"""
comparison.py — 系统分析结果 vs 人工整理结果 对比

读取「海缆路由中断分析结果/」目录下同事手工整理的电路清单，
与系统对同一条海缆的分析结果做对比，输出：
  - 系统多出的电路（系统有、人工无）
  - 系统漏掉的电路（人工有、系统无）
  - 双方一致的电路
  - 无对应人工基准、暂时无法判定的电路
  - 汇总数量与差异可能原因

匹配优先使用国际电路名；国际电路名缺失时，回退到
客户名 + A端 + Z端 + 带宽 的组合键做辅助匹配。
"""

from __future__ import annotations

import os

import openpyxl

from cable_config import CABLE_BY_ID, match_route_to_cable_ids, _normalize_route
from circuit_analyzer import (
    analyze, extract_international_circuit_id, bw_to_gbps, build_source_index,
)

# 系统分析纳入的电路性质
_VALID_TYPES = {"IP", "IEPL", "IPLC"}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MANUAL_DIR = os.path.join(BASE_DIR, "海缆路由中断分析结果")

# 人工清单列索引（0-based）：状态 | A端 | Z端 | 客户名 | 电路名 | 电路速率 | 1 | 2 | 3 | 4
_M_COL = {
    "status":    0,
    "site_a":    1,
    "site_b":    2,
    "customer":  3,
    "circuit":   4,
    "bandwidth": 5,
    "route1":    6,
    "route2":    7,
    "route3":    8,
    "route4":    9,
}


def manual_file_for(cable_id: str) -> str | None:
    """返回某海缆段落对应的人工结果文件路径，不存在返回 None。"""
    cable = CABLE_BY_ID.get(cable_id)
    if not cable:
        return None
    name = f"路由中断分析结果{cable['cable']} {cable['segment']}.xlsx"
    path = os.path.join(MANUAL_DIR, name)
    return path if os.path.exists(path) else None


def _norm_name(s: str) -> str:
    """归一化国际电路名用作匹配键：大写并去空白。"""
    return "".join(str(s or "").upper().split())


def _norm_bw(s: str) -> str:
    """归一化带宽（转 Gbps 数值字符串），便于辅助匹配。"""
    g = bw_to_gbps(str(s or ""))
    return f"{g:.6f}" if g else ""


def _aux_key(customer: str, site_a: str, site_b: str, bandwidth: str) -> str:
    """辅助匹配组合键：客户名 + A端 + Z端 + 带宽。"""
    return "|".join([
        _norm_name(customer),
        _norm_name(site_a),
        _norm_name(site_b),
        _norm_bw(bandwidth),
    ])


def load_manual(cable_id: str) -> list[dict]:
    """读取人工结果文件，返回电路列表。"""
    path = manual_file_for(cable_id)
    if not path:
        return []

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active

    rows = []
    for row in ws.iter_rows(min_row=1, values_only=True):
        status = str(row[_M_COL["status"]] or "").strip()
        # 跳过表头行与元信息行（"状态" 标题、"已中断路由:" 说明行）
        if status in ("", "状态") or status.startswith("已中断路由") or "中断路由:" in status:
            continue
        raw_circuit = str(row[_M_COL["circuit"]] or "")
        intl = extract_international_circuit_id(raw_circuit)
        routes = [str(row[_M_COL[k]] or "").strip() for k in ("route1", "route2", "route3", "route4")]
        rows.append({
            "status":     status,
            "site_a":     str(row[_M_COL["site_a"]] or "").strip(),
            "site_b":     str(row[_M_COL["site_b"]] or "").strip(),
            "customer":   str(row[_M_COL["customer"]] or "").strip(),
            "circuit_id_raw": raw_circuit.strip(),
            "circuit_id": intl,
            "bandwidth":  str(row[_M_COL["bandwidth"]] or "").strip(),
            "routes":     [r for r in routes if r],
        })
    wb.close()
    return rows


def _diff_reason_system_only(c: dict) -> str:
    """系统多出电路的可能原因。"""
    reasons = []
    if not c.get("circuit_id"):
        reasons.append("系统侧国际电路名提取失败，人工可能已收录但未匹配上")
    reasons.append("人工清单可能未收录该电路（漏记或版本较旧）")
    return "；".join(reasons)


def _manual_reference_types(manual_circuits: list[dict], source_index: dict) -> set[str]:
    """根据国际电路名回查槽路表，判断人工清单实际覆盖了哪些电路类型。"""
    types = set()
    for circuit in manual_circuits:
        key = _norm_name(circuit.get("circuit_id"))
        for source_row in source_index.get(key, []):
            circuit_type = source_row.get("type", "")
            if circuit_type == "IPLC":
                circuit_type = "IEPL"
            if circuit_type:
                types.add(circuit_type)
    return types


def _system_diff_record(c: dict, reason: str) -> dict:
    """生成系统侧差异/待核验电路的统一展示记录。"""
    routes = [c.get(f"route{i}") for i in range(1, 5)]
    return {
        "circuit_id": c.get("circuit_id"),
        "customer": c.get("customer"),
        "site_a": c.get("site_a"),
        "site_b": c.get("site_b"),
        "bandwidth": c.get("bandwidth"),
        "impact_status": c.get("impact_status"),
        "type": c.get("type"),
        "routes": [route for route in routes if route],
        "reason": reason,
    }


def _first_nonempty(items: list[str]) -> str:
    for x in items:
        if x:
            return x
    return ""


def diagnose_missing(m: dict, cable_id: str, source_index: dict) -> dict:
    """
    以国际电路名为锚点，在槽路表全量数据中回查该「系统漏掉」电路，
    结合其真实状态/性质/路由，给出证据级的漏掉原因。

    返回 {
      "found_in_source": bool,
      "source_status", "source_type", "source_routes": [...],
      "cause":  短标签（用于归类）,
      "detail": 详细说明,
    }
    """
    cable = CABLE_BY_ID.get(cable_id, {})
    cname = cable.get("cable", "")
    seg = cable.get("segment", "")

    nk = _norm_name(m.get("circuit_id"))
    base = {"found_in_source": False, "source_status": None,
            "source_type": None, "source_routes": []}

    # 1) 人工侧连国际电路名都没提取出来
    if not nk:
        return {**base, "cause": "电路名提取失败",
                "detail": "人工清单该行未能提取出国际电路名（电路名多行或写法特殊），无法在槽路表中定位比对。"}

    rows = source_index.get(nk, [])

    # 2) 槽路表中根本找不到这个国际电路名
    if not rows:
        return {**base, "cause": "槽路表中未找到该电路",
                "detail": f"按国际电路名「{m.get('circuit_id')}」在当前槽路表「金桥机房电路」中未找到匹配行。"
                          f"可能：人工清单与最新槽路表版本不一致、该电路已销户/改名，或人工电路名与槽路表写法不同。"}

    # 优先分析"开通"的行
    opened = [r for r in rows if r["status"] == "开通"]
    consider = opened if opened else rows

    def _routes(r):
        return [r["route1"], r["route2"], r["route3"], r["route4"]]

    # 3) 若某匹配行本应被系统命中（开通 + 性质合规 + 路由能匹配到该段落），
    #    说明问题出在对比匹配环节而非分析环节
    for r in consider:
        nonempty = [x for x in _routes(r) if x]
        matching_route = next((x for x in nonempty if cable_id in match_route_to_cable_ids(x)), None)
        if r["status"] == "开通" and r["type"] in _VALID_TYPES and matching_route:
            return {"found_in_source": True, "source_status": r["status"],
                    "source_type": r["type"], "source_routes": nonempty,
                    "cause": "系统应已命中（对比未对上）",
                    "detail": f"槽路表中该电路为「开通/{r['type']}」，且路由「{matching_route}」"
                              f"可匹配到 {cname} {seg}，系统分析理应已包含它；未对上多为电路名提取差异或存在重复电路，建议人工复核。"}

    # 4) 逐项判定失败原因（取首条开通行，无则首行）
    r = consider[0]
    nonempty = [x for x in _routes(r) if x]
    problems = []
    cause = None

    if r["status"] != "开通":
        problems.append(f"槽路表中该电路状态为「{r['status'] or '空'}」，系统只统计开通电路")
        cause = cause or "非开通电路"

    if r["type"] not in _VALID_TYPES:
        problems.append(f"电路性质为「{r['type'] or '空'}」，不在系统统计范围（仅 IP/IEPL/IPLC）")
        cause = cause or "性质不在统计范围"

    if not nonempty:
        problems.append("该电路在槽路表中无路由信息，系统无法判断其是否经过故障段落")
        cause = cause or "无路由信息"
    else:
        hits = any(cable_id in match_route_to_cable_ids(x) for x in nonempty)
        if not hits:
            mentions_cable = bool(cname) and any(
                _normalize_route(cname) in _normalize_route(x) for x in nonempty)
            routes_txt = "、".join(nonempty)
            manual_routes = [x for x in m.get("routes", []) if x]
            manual_has_target = any(cable_id in match_route_to_cable_ids(x) for x in manual_routes)
            if mentions_cable:
                problems.append(
                    f"路由写作「{routes_txt}」——只有海缆名 {cname}、缺少明确段落 {seg}"
                    f"（旧式模糊写法，如「{cname}崇明」「崇明{cname}」未拆分到段落），系统按精确段落匹配未命中")
                cause = cause or "路由写法模糊（仅海缆名无段落）"
            elif manual_has_target:
                problems.append(
                    f"人工清单标注该电路经 {cname} {seg}（人工路由：{('、'.join(manual_routes)) or '无'}），"
                    f"但当前槽路表中该电路路由仅为「{routes_txt}」，未记录该段落——"
                    f"多为源表(备用)路由字段缺失或槽路表版本与人工清单不一致")
                cause = cause or "源表路由与人工不一致（源表缺该段落）"
            else:
                problems.append(
                    f"路由「{routes_txt}」中不含目标段落 {cname} {seg}，系统未判定其受该段落影响"
                    f"（可能人工归类差异，或该电路实际走其它段落/版本不一致）")
                cause = cause or "路由不含该段落"

    if not problems:
        problems.append("槽路表中该电路为开通/合规性质且路由可匹配，未能自动判定漏掉原因，建议人工复核。")
        cause = cause or "待人工复核"

    return {"found_in_source": True, "source_status": r["status"],
            "source_type": r["type"], "source_routes": nonempty,
            "cause": cause, "detail": "；".join(problems)}


def compare(cable_id: str) -> dict:
    """
    对比某条海缆的系统分析结果与人工结果。

    返回：
    {
      "cable_id", "cable_label", "manual_available",
      "manual_file",
      "summary": {system_count, manual_count, matched, system_only, manual_only},
      "matched":     [...],
      "system_only": [...],   # 系统多出
      "manual_only": [...],   # 系统漏掉
    }
    """
    cable = CABLE_BY_ID.get(cable_id)
    cable_label = f"{cable['cable']} {cable['segment']}" if cable else cable_id

    manual_path = manual_file_for(cable_id)
    if not manual_path:
        return {
            "cable_id": cable_id,
            "cable_label": cable_label,
            "manual_available": False,
            "manual_file": None,
            "error": "未找到该海缆对应的人工结果文件",
        }

    # 系统结果包含 IP + IEPL/IPLC，所有类型都参与对比。
    system_circuits = analyze([cable_id])["circuits"]
    manual_circuits = load_manual(cable_id)
    # 全量源表索引（按国际电路名），用于对"系统漏掉"逐条回查诊断
    source_index = build_source_index()
    manual_types = _manual_reference_types(manual_circuits, source_index)
    manual_has_ip_reference = "IP" in manual_types

    # 建立系统侧索引：国际电路名 + 辅助键
    sys_by_name: dict[str, list[dict]] = {}
    sys_by_aux: dict[str, list[dict]] = {}
    for c in system_circuits:
        n = _norm_name(c.get("circuit_id"))
        if n:
            sys_by_name.setdefault(n, []).append(c)
        aux = _aux_key(c.get("customer"), c.get("site_a"), c.get("site_b"), c.get("bandwidth"))
        sys_by_aux.setdefault(aux, []).append(c)

    matched = []
    matched_sys_ids = set()  # 用 id() 标记已匹配的系统电路

    def _record_match(m, hit):
        matched_sys_ids.add(id(hit))
        matched.append({
            "circuit_id": m.get("circuit_id") or hit.get("circuit_id"),
            "customer": hit.get("customer") or m.get("customer"),
            "site_a": hit.get("site_a"),
            "site_b": hit.get("site_b"),
            "bandwidth": hit.get("bandwidth"),
            "system_status": hit.get("impact_status"),
            "manual_status": m.get("status"),
            "type": hit.get("type"),
        })

    # 第一轮：全部按国际电路名精确匹配（先把能对上名字的都对上，
    #         避免辅助键抢占了本应按名字匹配的系统电路）。
    unmatched = []
    for m in manual_circuits:
        n = _norm_name(m.get("circuit_id"))
        hit = None
        if n and sys_by_name.get(n):
            for cand in sys_by_name[n]:
                if id(cand) not in matched_sys_ids:
                    hit = cand
                    break
        if hit is not None:
            _record_match(m, hit)
        else:
            unmatched.append(m)

    # 第二轮：仅对仍未匹配的人工电路，用辅助键（客户+A端+Z端+带宽）兜底匹配。
    manual_only = []
    for m in unmatched:
        hit = None
        aux = _aux_key(m.get("customer"), m.get("site_a"), m.get("site_b"), m.get("bandwidth"))
        for cand in sys_by_aux.get(aux, []):
            if id(cand) not in matched_sys_ids:
                hit = cand
                break
        if hit is not None:
            _record_match(m, hit)
        else:
            diag = diagnose_missing(m, cable_id, source_index)
            manual_only.append({**m, **diag})

    # 系统未匹配项需要区分两种情况：
    # 1) 人工清单覆盖了该类型，才可判定为“系统多出”；
    # 2) 人工清单完全没有 IP 基准时，IP 只能列为“待核验”，不能凭缺席判错。
    system_only = []
    unverified = []
    for c in system_circuits:
        if id(c) in matched_sys_ids:
            continue
        if c.get("type") == "IP" and not manual_has_ip_reference:
            unverified.append(_system_diff_record(
                c,
                "人工清单未提供 IP 明细，当前无法判定一致或多出；系统命中依据已保留，待人工补充基准后复核。",
            ))
        else:
            system_only.append(_system_diff_record(c, _diff_reason_system_only(c)))

    if manual_has_ip_reference:
        scope_note = "人工清单包含 IP 基准，IP 与客户专线均按电路逐条对比。"
    else:
        scope_note = (
            "IP 电路已纳入对比；因当前人工清单没有 IP 明细，未匹配的 IP 单列为“待核验”，"
            "不直接判定为系统多出。"
        )

    return {
        "cable_id": cable_id,
        "cable_label": cable_label,
        "manual_available": True,
        "manual_file": os.path.basename(manual_path),
        "scope_note": scope_note,
        "manual_reference_types": sorted(manual_types),
        "summary": {
            "system_count": len(system_circuits),
            "manual_count": len(manual_circuits),
            "matched": len(matched),
            "system_only": len(system_only),
            "manual_only": len(manual_only),
            "unverified": len(unverified),
        },
        "matched": matched,
        "system_only": system_only,
        "manual_only": manual_only,
        "unverified": unverified,
    }
