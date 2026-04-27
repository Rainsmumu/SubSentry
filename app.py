"""
app.py — SubSentry 海缆故障传报系统
Flask Web 服务入口

启动：python app.py
访问：http://localhost:8080
"""

import json
import os
import uuid
from collections import defaultdict
from datetime import datetime

from flask import Flask, jsonify, render_template, request, Response

from cable_config import CABLES, CABLE_BY_ID
from circuit_analyzer import analyze, bw_to_gbps
from report_builder import build_reports
from excel_builder import build_excel

# ── 配置 ─────────────────────────────────────────────────────────────
PORT       = 8080
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "fault_state.json")

app = Flask(__name__)


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
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


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
        c.get("current_route", ""),
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
    app.run(host="0.0.0.0", port=PORT, debug=False)
