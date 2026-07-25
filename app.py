"""
app.py — SubSentry 海缆故障传报系统
Flask Web 服务入口

启动：python app.py
访问：http://localhost:8080
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from collections import defaultdict
from datetime import datetime

from flask import Flask, jsonify, render_template, request, Response

from cable_config import CABLES, CABLE_BY_ID
from circuit_analyzer import analyze, bw_to_gbps, invalidate_cache
from report_builder import build_reports
from excel_builder import build_excel
import data_source
from comparison import compare as compare_manual

# ── 配置 ─────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(
    os.environ.get("SUBSENTRY_DATA_DIR", os.path.join(BASE_DIR, "data"))
)
HOST = os.environ.get("SUBSENTRY_HOST", "0.0.0.0")
PORT = int(os.environ.get("SUBSENTRY_PORT", "8080"))
STATE_FILE = os.path.join(DATA_DIR, "fault_state.json")

app = Flask(__name__)
# 静态资源（tailwind/alpine 本地文件）允许浏览器缓存 1 天，减少跨境重复下载
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 86400

# gzip 压缩：跨境访问时把 ~450KB 前端资源压到约 1/4，显著加快首次加载。
# 未安装 flask-compress 时自动跳过（不影响本地运行）。
app.config["COMPRESS_MIMETYPES"] = [
    "text/html", "text/css", "text/xml", "application/json",
    "application/javascript", "text/javascript",  # 本地 tailwind 以 text/javascript 提供
]
app.config["COMPRESS_MIN_SIZE"] = 500
try:
    from flask_compress import Compress
    Compress(app)
except ImportError:
    pass


def _warm_cache() -> None:
    """启动时预读一次数据源，把 13MB Excel 解析放到启动阶段，
    避免第一个访问的用户等待约 8 秒。"""
    try:
        from circuit_analyzer import load_circuits
        load_circuits()
    except Exception as e:  # 数据源缺失/异常不应阻止服务启动
        print(f"[warm_cache] 预加载数据源失败（首个请求将稍慢）：{e}")


_warm_cache()


# ── 状态持久化 ────────────────────────────────────────────────────────

def _load_state() -> dict:
    """从 JSON 文件加载故障事件列表，文件不存在则返回空状态。"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"events": []}


def _save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix="fault-state-", suffix=".json", dir=os.path.dirname(STATE_FILE)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, STATE_FILE)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def _get_broken_ids(state: dict) -> list[str]:
    """从当前状态提取所有处于中断状态的海缆 id 列表（去重）。"""
    seen = set()
    result = []
    for ev in state["events"]:
        cid = ev["cable_id"]
        if cid not in seen:
            seen.add(cid)
            result.append(cid)
    return result


# ── 路由 ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ── 前端第三方资源（预压缩，加速跨境首次加载）──────────────────────
import gzip as _gzip

_VENDOR_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "vendor")
_VENDOR_GZ_CACHE: dict[str, bytes] = {}
_VENDOR_MIME = {".js": "text/javascript", ".css": "text/css"}  # Flask 会自动补 charset


@app.route("/assets/vendor/<path:filename>")
def vendor_asset(filename: str):
    """
    提供 tailwind/alpine 等本地第三方资源，并按需 gzip（内存缓存压缩结果）。
    Flask 默认 /static 走文件直通模式，flask-compress 不会压缩，故单独处理最大的资源。
    """
    safe = os.path.basename(filename)
    path = os.path.join(_VENDOR_DIR, safe)
    if not os.path.isfile(path):
        return jsonify({"error": "not found"}), 404

    ctype = _VENDOR_MIME.get(os.path.splitext(safe)[1].lower(), "application/octet-stream")
    accepts_gzip = "gzip" in request.headers.get("Accept-Encoding", "")

    if accepts_gzip:
        body = _VENDOR_GZ_CACHE.get(safe)
        if body is None:
            with open(path, "rb") as f:
                body = _gzip.compress(f.read(), 6)
            _VENDOR_GZ_CACHE[safe] = body
        resp = Response(body, mimetype=ctype)
        resp.headers["Content-Encoding"] = "gzip"
        resp.headers["Vary"] = "Accept-Encoding"
    else:
        with open(path, "rb") as f:
            resp = Response(f.read(), mimetype=ctype)

    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


# ── 数据源（槽路表上传）─────────────────────────────────────────────

@app.route("/api/datasource")
def api_datasource():
    """返回当前数据源状态（文件名、上传时间、读取状态、电路条数）。"""
    return jsonify(data_source.get_status())


@app.route("/api/upload", methods=["POST"])
def api_upload():
    """
    上传最新槽路表 Excel，校验通过后保存为当前数据源并刷新缓存。
    表单字段名：file
    """
    if "file" not in request.files:
        return jsonify({"error": "未收到上传文件（字段名应为 file）"}), 400
    f = request.files["file"]
    if not f or not f.filename:
        return jsonify({"error": "未选择文件"}), 400

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in data_source.ALLOWED_EXT:
        return jsonify({"error": f"文件不是 Excel（仅支持 {'/'.join(sorted(data_source.ALLOWED_EXT))}）"}), 400

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=ext)
    try:
        os.close(tmp_fd)
        f.save(tmp_path)
        status = data_source.save_uploaded(tmp_path, f.filename)
    except data_source.DataSourceError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"保存失败：{e}"}), 500
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    # 清空分析缓存，确保后续分析立即使用新文件
    invalidate_cache()
    return jsonify({"ok": True, "datasource": status})


@app.route("/api/compare")
def api_compare():
    """返回某条海缆的「系统结果 vs 人工结果」对比。?cable_id=APCN2_S3"""
    cable_id = request.args.get("cable_id", "").strip()
    if not cable_id or cable_id not in CABLE_BY_ID:
        return jsonify({"error": "无效的 cable_id"}), 400
    return jsonify(compare_manual(cable_id))


@app.route("/api/cables")
def api_cables():
    """返回 8 条海缆段落配置 + 当前故障状态。"""
    state = _load_state()
    broken_set = set(_get_broken_ids(state))

    result = []
    for c in CABLES:
        result.append({
            "id":        c["id"],
            "cable":     c["cable"],
            "segment":   c["segment"],
            "landing":   c["landing"],
            "route_desc":c["route_desc"],
            "direction": c["direction"],
            "status":    "broken" if c["id"] in broken_set else "normal",
        })
    return jsonify(result)


@app.route("/api/fault", methods=["POST"])
def api_add_fault():
    """录入一条故障事件，返回该事件的独立影响分析结果。"""
    data = request.get_json(silent=True) or {}
    cable_id   = data.get("cable_id", "").strip()
    fault_time = data.get("fault_time", "").strip()

    if not cable_id or cable_id not in CABLE_BY_ID:
        return jsonify({"error": "无效的 cable_id"}), 400
    if not fault_time:
        return jsonify({"error": "缺少 fault_time"}), 400

    state = _load_state()

    # 如果该海缆已在故障列表中，先移除再添加（更新时间）
    state["events"] = [e for e in state["events"] if e["cable_id"] != cable_id]
    event = {
        "id":         str(uuid.uuid4()),
        "cable_id":   cable_id,
        "fault_time": fault_time,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    state["events"].append(event)
    _save_state(state)

    return _build_analysis_response_for_event(state, event["id"])


@app.route("/api/fault/<event_id>", methods=["DELETE"])
def api_remove_fault(event_id: str):
    """解除某条故障事件（按事件 id 删除），触发全量重算。"""
    state = _load_state()
    before = len(state["events"])
    state["events"] = [e for e in state["events"] if e["id"] != event_id]
    if len(state["events"]) == before:
        return jsonify({"error": "找不到该故障事件"}), 404
    _save_state(state)

    # 返回更新后的海缆状态列表（用于前端刷新态势图）
    broken_set = set(_get_broken_ids(state))
    cables_status = [
        {"id": c["id"], "status": "broken" if c["id"] in broken_set else "normal"}
        for c in CABLES
    ]
    return jsonify({"cables": cables_status, "events": state["events"]})


@app.route("/api/state")
def api_state():
    """返回当前完整故障状态（事件列表 + 海缆状态）。"""
    state = _load_state()
    broken_set = set(_get_broken_ids(state))
    cables_status = [
        {"id": c["id"], "status": "broken" if c["id"] in broken_set else "normal"}
        for c in CABLES
    ]
    return jsonify({"events": state["events"], "cables": cables_status})


@app.route("/api/analysis")
def api_analysis():
    """
    根据查询参数返回某次故障的完整分析结果（通报文本 + 电路明细）。
    ?event_id=xxx  或  ?cable_id=TPE_S4&fault_time=2025-12-21T04:24

    注意：返回的是该故障事件的独立影响（相对该事件发生前的变化量）。
    """
    event_id = request.args.get("event_id", "").strip()
    cable_id = request.args.get("cable_id", "").strip()
    fault_time = request.args.get("fault_time", "").strip()

    state = _load_state()

    target_event = _find_target_event(state, event_id, cable_id, fault_time)

    if not target_event:
        return jsonify({"error": "找不到该故障事件"}), 404

    return _build_analysis_response_for_event(state, target_event["id"])


@app.route("/api/download")
def api_download():
    """
    生成并下载 Excel 统计表。
    ?event_id=xxx 或 ?cable_id=TPE_S4&fault_time=2025-12-21T04:24
    """
    event_id   = request.args.get("event_id", "").strip()
    cable_id   = request.args.get("cable_id", "").strip()
    fault_time = request.args.get("fault_time", "").strip()
    state = _load_state()

    target_event = _find_target_event(state, event_id, cable_id, fault_time)
    if target_event:
        cable_id = target_event["cable_id"]
        fault_time = target_event["fault_time"]
        result = _analyze_event_independent_impact(state, target_event)
    else:
        if event_id or (cable_id and fault_time):
            return jsonify({"error": "找不到该故障事件"}), 404
        if not cable_id or cable_id not in CABLE_BY_ID:
            return jsonify({"error": "无效的 cable_id"}), 400
        if not fault_time:
            return jsonify({"error": "缺少 fault_time"}), 400
        result = analyze(_get_broken_ids(state))

    excel_bytes = build_excel(cable_id, fault_time, result["circuits"])

    cable = CABLE_BY_ID[cable_id]
    filename = f"国际海缆故障影响业务统计表 {cable['cable']} {cable['segment']}（{cable['route_desc']}）.xlsx"

    return Response(
        excel_bytes,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{_url_encode(filename)}"
        },
    )


# ── 内部辅助 ──────────────────────────────────────────────────────────

def _find_target_event(state: dict, event_id: str, cable_id: str, fault_time: str) -> dict | None:
    """优先按 event_id 查找，兼容 cable_id + fault_time 查找。"""
    if event_id:
        for ev in state["events"]:
            if ev["id"] == event_id:
                return ev
        return None

    if cable_id and fault_time:
        for ev in state["events"]:
            if ev["cable_id"] == cable_id and ev["fault_time"] == fault_time:
                return ev
    return None


def _get_broken_ids_before_after_event(state: dict, target_event: dict) -> tuple[list[str], list[str]]:
    """
    返回目标事件发生前/发生后的故障海缆列表（去重，按时间顺序）。
    after = before + target_event.cable_id
    """
    before = []
    seen = set()
    ordered_events = sorted(state["events"], key=lambda x: x.get("created_at", ""))
    target_id = target_event["id"]

    for ev in ordered_events:
        cid = ev.get("cable_id", "")
        if ev.get("id") == target_id:
            after = before.copy()
            if cid and cid not in seen:
                after.append(cid)
            return before, after
        if cid and cid not in seen:
            before.append(cid)
            seen.add(cid)

    # 理论上不应到达这里，兜底按当前全量返回
    full = _get_broken_ids(state)
    return full, full


def _circuit_key(c: dict) -> tuple:
    """构建电路键，尽量避免重复电路误判。"""
    return (
        c.get("type", ""),
        c.get("circuit_id", ""),
        c.get("customer", ""),
        c.get("site_a", ""),
        c.get("site_b", ""),
        c.get("route1", ""),
        c.get("route2", ""),
        c.get("route3", ""),
        c.get("route4", ""),
        c.get("bandwidth", ""),
    )


def _summarize_circuits(circuits: list[dict]) -> dict:
    """按前端/通报需要汇总独立影响电路。"""
    iepl_total     = sum(1 for c in circuits if c["type"] == "IEPL")
    iepl_broken    = sum(1 for c in circuits if c["type"] == "IEPL" and c["is_broken"])
    iepl_broken_sh = sum(1 for c in circuits if c["type"] == "IEPL" and c["is_broken"] and c["is_shanghai"])

    ip_loss    = sum(bw_to_gbps(c["bandwidth"]) for c in circuits if c["type"] == "IP" and c["is_broken"])
    ip_loss_sh = sum(
        bw_to_gbps(c["bandwidth"])
        for c in circuits
        if c["type"] == "IP" and c["is_broken"] and c["is_shanghai"]
    )

    return {
        "iepl_total":      iepl_total,
        "iepl_broken":     iepl_broken,
        "iepl_broken_sh":  iepl_broken_sh,
        "ip_loss_gbps":    round(ip_loss, 4),
        "ip_loss_sh_gbps": round(ip_loss_sh, 4),
    }


def _analyze_event_independent_impact(state: dict, target_event: dict) -> dict:
    """
    计算某个事件的独立影响：
    仅保留该事件引起的新增影响或影响级别变化（如 主用 -> 主备双断）。
    """
    broken_before, broken_after = _get_broken_ids_before_after_event(state, target_event)

    before_result = analyze(broken_before) if broken_before else {"circuits": []}
    after_result = analyze(broken_after)

    before_index: dict[tuple, list[tuple[str, bool]]] = defaultdict(list)
    for c in before_result["circuits"]:
        before_index[_circuit_key(c)].append((c["impact_status"], c["is_broken"]))

    independent_circuits = []
    for c in after_result["circuits"]:
        key = _circuit_key(c)
        prev_list = before_index.get(key)
        if not prev_list:
            independent_circuits.append(c)
            continue

        prev_status, prev_is_broken = prev_list.pop()
        if prev_status != c["impact_status"] or prev_is_broken != c["is_broken"]:
            independent_circuits.append(c)

    return {
        "broken_ids": after_result["broken_ids"],
        "circuits": independent_circuits,
        "summary": _summarize_circuits(independent_circuits),
    }


def _build_analysis_response_for_event(state: dict, event_id: str) -> Response:
    """按事件返回独立影响分析结果。"""
    target_event = _find_target_event(state, event_id, "", "")
    if not target_event:
        return jsonify({"error": "找不到该故障事件"}), 404

    cable_id = target_event["cable_id"]
    fault_time = target_event["fault_time"]
    if cable_id not in CABLE_BY_ID:
        return jsonify({"error": "无效的 cable_id"}), 400

    result = _analyze_event_independent_impact(state, target_event)
    return _build_analysis_response_from_result(
        result=result,
        cable_id=cable_id,
        fault_time=fault_time,
        events=state["events"],
        broken=_get_broken_ids(state),
        event_id=event_id,
    )


def _build_analysis_response_from_result(
    result: dict,
    cable_id: str,
    fault_time: str,
    events: list,
    broken: list[str],
    event_id: str | None = None,
) -> Response:
    """执行分析后统一组装 JSON 响应。"""

    # 上海落地且业务中断的 IEPL（微信明细用）
    broken_iepl_sh = [
        c for c in result["circuits"]
        if c["type"] == "IEPL" and c["is_broken"] and c["is_shanghai"]
    ]

    reports = build_reports(cable_id, fault_time, result["summary"], broken_iepl_sh)

    # 电路按 IEPL / IP 分组，前端展示用
    iepl_circuits = [c for c in result["circuits"] if c["type"] == "IEPL"]
    ip_circuits   = [c for c in result["circuits"] if c["type"] == "IP"]

    return jsonify({
        "cable_id":   cable_id,
        "fault_time": fault_time,
        "event_id":   event_id,
        "broken_ids": result["broken_ids"],
        "summary":    result["summary"],
        "reports":    reports,
        "iepl":       iepl_circuits,
        "ip":         ip_circuits,
        "events":     events,
        "cables": [
            {"id": c["id"], "status": "broken" if c["id"] in set(broken) else "normal"}
            for c in CABLES
        ],
    })


def _url_encode(s: str) -> str:
    """对文件名做 URL 编码（RFC 5987）。"""
    from urllib.parse import quote
    return quote(s, safe="")


# ── 启动 ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print()
    print("  ┌─────────────────────────────────────────────────────┐")
    print("  │         SubSentry  海缆故障传报系统                 │")
    print("  │         上海国际局 · 崇明/南汇出口                  │")
    print("  └─────────────────────────────────────────────────────┘")
    print()
    print(f"  启动地址: http://localhost:{PORT}")
    print("  按 Ctrl+C 停止\n")
    app.run(host=HOST, port=PORT, debug=False)
