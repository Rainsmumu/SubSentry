"""
comparison.py — 系统分析结果 vs 人工整理结果 对比

读取「海缆路由中断分析结果/」目录下同事手工整理的受影响电路清单，
与系统对同一条海缆的分析结果做对比，输出：
  - 系统多出的电路（系统有、人工无）
  - 系统漏掉的电路（人工有、系统无）
  - 双方一致的电路
  - 汇总数量与差异可能原因

匹配优先使用国际电路名；国际电路名缺失时，回退到
客户名 + A端 + Z端 + 带宽 的组合键做辅助匹配。
"""

from __future__ import annotations

import os

import openpyxl

from cable_config import CABLE_BY_ID, match_route_to_cable_ids
from circuit_analyzer import analyze, extract_international_circuit_id, bw_to_gbps

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
    if c.get("type") == "IP":
        reasons.append("该电路为 IP 电路，人工清单可能仅整理客户专线")
    return "；".join(reasons)


def _diff_reason_manual_only(c: dict) -> str:
    """系统漏掉电路的可能原因。"""
    reasons = []
    if not c.get("circuit_id"):
        reasons.append("人工电路名多行/格式特殊，国际电路名提取失败")
    # 检查人工路由写法是否能被系统识别
    routes = c.get("routes", [])
    if routes and not any(match_route_to_cable_ids(r) for r in routes):
        reasons.append("人工路由写法系统未能识别（如拼接海缆或写法不一致）")
    st = c.get("status", "")
    if st and st not in ("中断", "主用", "备用", "主备双断", "无保护"):
        reasons.append(f"人工状态为「{st}」，可能非开通/含备注，系统未纳入统计")
    reasons.append("系统仅统计开通的 IEPL/IPLC/IP，或槽路表版本与人工清单不一致")
    return "；".join(reasons)


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

    # 系统结果：该海缆单独故障时的全部受影响电路
    system_circuits = analyze([cable_id])["circuits"]
    manual_circuits = load_manual(cable_id)

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
    manual_only = []
    matched_sys_ids = set()  # 用 id() 标记已匹配的系统电路

    for m in manual_circuits:
        n = _norm_name(m.get("circuit_id"))
        hit = None
        # 优先国际电路名匹配
        if n and sys_by_name.get(n):
            for cand in sys_by_name[n]:
                if id(cand) not in matched_sys_ids:
                    hit = cand
                    break
        # 回退辅助键匹配
        if hit is None:
            aux = _aux_key(m.get("customer"), m.get("site_a"), m.get("site_b"), m.get("bandwidth"))
            for cand in sys_by_aux.get(aux, []):
                if id(cand) not in matched_sys_ids:
                    hit = cand
                    break
        if hit is not None:
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
        else:
            manual_only.append({
                **m,
                "reason": _diff_reason_manual_only(m),
            })

    # 系统多出：未被任何人工电路匹配到的系统电路
    system_only = []
    for c in system_circuits:
        if id(c) not in matched_sys_ids:
            system_only.append({
                "circuit_id": c.get("circuit_id"),
                "customer": c.get("customer"),
                "site_a": c.get("site_a"),
                "site_b": c.get("site_b"),
                "bandwidth": c.get("bandwidth"),
                "impact_status": c.get("impact_status"),
                "type": c.get("type"),
                "route1": c.get("route1"),
                "reason": _diff_reason_system_only(c),
            })

    return {
        "cable_id": cable_id,
        "cable_label": cable_label,
        "manual_available": True,
        "manual_file": os.path.basename(manual_path),
        "summary": {
            "system_count": len(system_circuits),
            "manual_count": len(manual_circuits),
            "matched": len(matched),
            "system_only": len(system_only),
            "manual_only": len(manual_only),
        },
        "matched": matched,
        "system_only": system_only,
        "manual_only": manual_only,
    }
