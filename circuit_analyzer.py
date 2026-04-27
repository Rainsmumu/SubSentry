"""
circuit_analyzer.py — 电路影响分析引擎

从金桥机房电路表读取开通的 IP/IEPL 电路，
根据当前故障海缆集合判断每条电路的影响状态。

影响分类：
  无保护   — 单腿且该腿已断，或所有腿均已断（业务中断）
  主备双断  — 多腿电路所有路由均已断（业务中断）
  主用受影响 — 第一路由断但有存活备用（业务通过备用存活）
  备用受影响 — 第一路由存活但某备用路由断（保护能力降低）
  疑似     — 路由写法模糊，无法确定是否受影响（需人工确认）
"""

import os
import re
import openpyxl
from cable_config import match_route_to_cable, CABLE_BY_ID

# 金桥机房电路表列索引（0-based）
_COL = {
    "site_a":      1,
    "site_b":      10,
    "customer":    12,
    "circuit_id":  22,
    "route1":      26,
    "route2":      27,
    "route3":      28,
    "current_route": 29,  # 新增：当前路由（实际运行路由）
    "bandwidth":   34,
    "type":        38,
    "status":      90,
}

# 统计的电路性质：IP、IEPL、IPLC（IPLC 与 IEPL 同属客户专线，样本数据包含此类型）
_VALID_TYPES = {"IP", "IEPL", "IPLC"}

# 归一化：IPLC 统一当作 IEPL 处理（统计专线明细）
_NORMALIZE_TYPE = {"IPLC": "IEPL"}

# 影响状态常量
STATUS_NO_PROTECT   = "无保护"      # 业务中断（单腿或全断）
STATUS_DUAL_BREAK   = "主备双断"    # 业务中断（多腿全断）
STATUS_PRIMARY      = "主用"        # 主用受影响（业务通过备用存活）
STATUS_BACKUP       = "备用"        # 备用受影响（主用存活）
STATUS_SUSPECT      = "疑似"        # 路由模糊，待人工确认

# 中断状态集合（用于统计"中断"数量和带宽）
BROKEN_STATUSES = {STATUS_NO_PROTECT, STATUS_DUAL_BREAK}


# ── 数据加载（带缓存，数据文件不变时只读一次）──────────────────────
_data_cache: list | None = None
_data_mtime: float = 0.0
_INTERNATIONAL_CIRCUIT_RE = re.compile(r"([A-Z0-9-]+(?:/[A-Z0-9-]+)+\s+[A-Z0-9-]+)", re.IGNORECASE)


def _get_excel_path() -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "金桥机房电路表.xlsx")


def load_circuits(force_reload: bool = False) -> list[dict]:
    """
    加载金桥机房电路表中所有"开通"的 IP/IEPL 电路。
    返回列表，每项为字典形式的电路信息。
    """
    global _data_cache, _data_mtime

    path = _get_excel_path()
    try:
        mtime = os.path.getmtime(path)
    except FileNotFoundError:
        raise FileNotFoundError(f"找不到金桥机房电路表：{path}")

    if not force_reload and _data_cache is not None and mtime == _data_mtime:
        return _data_cache

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["金桥机房电路"]

    circuits = []
    for row in ws.iter_rows(min_row=3, max_col=95, values_only=True):
        # 过滤：只取开通状态
        if str(row[_COL["status"]] or "").strip() != "开通":
            continue
        # 过滤：只取 IP / IEPL
        ctype = str(row[_COL["type"]] or "").strip()
        if ctype not in _VALID_TYPES:
            continue

        raw_circuit_id = str(row[_COL["circuit_id"]] or "").strip()

        circuits.append({
            "site_a":    str(row[_COL["site_a"]]    or "").strip(),
            "site_b":    str(row[_COL["site_b"]]    or "").strip(),
            "customer":  str(row[_COL["customer"]]  or "").strip(),
            "circuit_id_raw": raw_circuit_id,
            "circuit_id": extract_international_circuit_id(raw_circuit_id),
            "route1":    str(row[_COL["route1"]]    or "").strip(),
            "route2":    str(row[_COL["route2"]]    or "").strip(),
            "route3":    str(row[_COL["route3"]]    or "").strip(),
            "current_route": str(row[_COL["current_route"]] or "").strip(),  # 当前路由
            "bandwidth": str(row[_COL["bandwidth"]] or "").strip(),
            "type":      _NORMALIZE_TYPE.get(ctype, ctype),  # IPLC → IEPL
        })

    wb.close()
    _data_cache = circuits
    _data_mtime = mtime
    return circuits


def extract_international_circuit_id(raw_value: str) -> str:
    """
    从"电路代号"列中提取国际电路编码。
    规则：
    1. 优先取形如 "SHI/CU-SEL/CU EP025" 的国际编码
    2. 忽略 BEARER、本地电路编码、纯中文说明
    3. 若未匹配到国际编码，则回退到第一条非空、非说明性文本
    """
    if not raw_value:
        return ""

    lines = [line.strip() for line in str(raw_value).splitlines() if line and line.strip()]
    for line in lines:
        match = _INTERNATIONAL_CIRCUIT_RE.search(line.upper())
        if match:
            return match.group(1).strip()

    for line in lines:
        upper = line.upper()
        if "BEARER" in upper or "本地电路编码" in line:
            continue
        return line
    return lines[0] if lines else ""


# ── 带宽解析 ────────────────────────────────────────────────────────

def bw_to_gbps(bw_str: str) -> float:
    """将带宽字符串转换为 Gbps 浮点值，用于汇总 IP 带宽损失。"""
    if not bw_str:
        return 0.0
    s = bw_str.strip().upper().replace(" ", "")
    try:
        if s.endswith("G"):
            return float(s[:-1])
        if s.endswith("M"):
            return float(s[:-1]) / 1000
        if s.endswith("K") or "K" in s:
            return float(s.replace("K", "")) / 1_000_000
        return float(s) / 1000  # 裸数字假设为 Mbps
    except (ValueError, TypeError):
        return 0.0


def format_gbps(gbps: float) -> str:
    """将 Gbps 浮点值格式化为通报用字符串，如 '128G'、'0.155G'。"""
    if gbps == int(gbps):
        return f"{int(gbps)}G"
    # 去掉末尾多余零，再加 G
    s = f"{gbps:.4f}".rstrip("0").rstrip(".")
    return s + "G"


# ── 核心分析逻辑 ────────────────────────────────────────────────────

def _classify_circuit(
    circuit: dict,
    broken_ids: set[str],
    ambiguous_active: dict[str, list[str]],
) -> str | None:
    """
    对单条电路进行影响分类。

    broken_ids: 当前已断海缆的 id 集合
    ambiguous_active: {模糊关键字组合标识 -> [可能的 cable_id 列表]}，
                      只包含其中至少有一个 id 在 broken_ids 中的模糊模式

    返回影响状态字符串，或 None（不受影响，不纳入统计）。
    """
    # 优先使用"当前路由"，如果为空则使用设计路由
    current_route = circuit.get("current_route", "").strip()

    if current_route:
        # 有当前路由，只检查当前路由是否受影响
        routes = [current_route]
        is_temp_route = True
    else:
        # 无当前路由，使用设计路由
        route_fields = [circuit["route1"], circuit["route2"], circuit["route3"]]
        routes = [r for r in route_fields if r]
        is_temp_route = False

    if not routes:
        return None

    # 对每条路由做匹配
    exact_matches: list[str | None] = []   # 精确匹配到的 cable_id（None 表示不在已断集合）
    is_broken: list[bool] = []             # 该路由是否确认断路
    is_ambiguous_broken: list[bool] = []   # 该路由是否疑似受影响（模糊写法）

    for route in routes:
        cable_id, ambiguous = match_route_to_cable(route)
        if cable_id and cable_id in broken_ids:
            exact_matches.append(cable_id)
            is_broken.append(True)
            is_ambiguous_broken.append(False)
        elif ambiguous:
            # 检查这个模糊路由是否可能命中已断海缆
            # 用 match_route_to_cable 已返回 ambiguous=True，
            # 需要再判断对应的 possible_ids 中是否有在 broken_ids 里的
            possibly_broken = _ambiguous_route_possibly_broken(route, broken_ids)
            exact_matches.append(None)
            is_broken.append(False)
            is_ambiguous_broken.append(possibly_broken)
        else:
            exact_matches.append(None)
            is_broken.append(False)
            is_ambiguous_broken.append(False)

    confirmed_broken = sum(is_broken)
    ambiguous_broken = sum(is_ambiguous_broken)
    confirmed_alive = sum(1 for b, a in zip(is_broken, is_ambiguous_broken) if not b and not a)
    total = len(routes)

    # 完全不受影响
    if confirmed_broken == 0 and ambiguous_broken == 0:
        return None

    # 如果是临时路由且断了，直接标记为无保护（因为已经没有备用）
    if is_temp_route and confirmed_broken > 0:
        return STATUS_NO_PROTECT

    # 全部确认断路
    if confirmed_broken == total:
        if total == 1:
            return STATUS_NO_PROTECT
        return STATUS_DUAL_BREAK

    # 第一路由确认断，有存活备用
    if is_broken[0] and confirmed_alive > 0:
        return STATUS_PRIMARY

    # 第一路由存活，某备用确认断
    if not is_broken[0] and not is_ambiguous_broken[0] and confirmed_broken > 0:
        return STATUS_BACKUP

    # 第一路由存活，仅有疑似断（模糊路由）
    if not is_broken[0] and ambiguous_broken > 0 and confirmed_broken == 0:
        return STATUS_SUSPECT

    # 第一路由是疑似断
    if is_ambiguous_broken[0]:
        return STATUS_SUSPECT

    # 兜底：有任何已断或疑似断路由
    if confirmed_broken > 0:
        return STATUS_PRIMARY
    return STATUS_SUSPECT


def _ambiguous_route_possibly_broken(route_str: str, broken_ids: set[str]) -> bool:
    """
    检查一个模糊路由字段（如 "TPE崇明"）对应的可能段落中，
    是否有至少一个已在 broken_ids 中。
    """
    from cable_config import AMBIGUOUS_PATTERNS
    upper = route_str.upper()
    for pattern in AMBIGUOUS_PATTERNS:
        if all(kw.upper() in upper for kw in pattern["keywords"]):
            if any(pid in broken_ids for pid in pattern["possible_ids"]):
                return True
    return False


def circuit_sort_key(circuit: dict) -> tuple:
    """排序：真实中断优先，再按上海优先、带宽从大到小。"""
    broken_order = 0 if circuit.get("is_broken") else 1
    sh_order = 0 if circuit.get("is_shanghai") else 1
    return (
        broken_order,
        sh_order,
        -bw_to_gbps(circuit.get("bandwidth", "")),
        circuit.get("circuit_id", ""),
        circuit.get("customer", ""),
    )


def analyze(broken_cable_ids: list[str]) -> dict:
    """
    给定当前已断海缆 id 列表，分析所有受影响电路。

    返回结构：
    {
      "broken_ids": [...],
      "circuits": [
        {
          "site_a", "site_b", "customer", "circuit_id",
          "route1", "route2", "route3", "bandwidth", "type",
          "impact_status",    # 影响分类
          "is_shanghai",      # Site A == "上海"
          "is_broken",        # 业务是否中断（无保护 / 主备双断）
        },
        ...
      ],
      "summary": {
        "iepl_total": int,        # IEPL 受影响总条数（含主用/备用/疑似）
        "iepl_broken": int,       # IEPL 业务中断条数
        "iepl_broken_sh": int,    # 上海落地 IEPL 中断条数
        "ip_loss_gbps": float,    # IP 带宽损失（仅中断）
        "ip_loss_sh_gbps": float, # 上海落地 IP 带宽损失
      }
    }
    """
    broken_ids = set(broken_cable_ids)
    circuits = load_circuits()

    result_circuits = []
    for c in circuits:
        status = _classify_circuit(c, broken_ids, {})
        if status is None:
            continue
        is_sh = (c["site_a"] == "上海")
        is_broken = status in BROKEN_STATUSES
        is_temp = bool(c.get("current_route", "").strip())  # 是否运行在临时路由
        result_circuits.append({
            **c,
            "impact_status": status,
            "is_shanghai": is_sh,
            "is_broken": is_broken,
            "is_temp_route": is_temp,  # 新增标记
        })

    result_circuits.sort(key=circuit_sort_key)

    # 汇总统计
    iepl_total     = sum(1 for c in result_circuits if c["type"] == "IEPL")
    iepl_broken    = sum(1 for c in result_circuits if c["type"] == "IEPL" and c["is_broken"])
    iepl_broken_sh = sum(1 for c in result_circuits if c["type"] == "IEPL" and c["is_broken"] and c["is_shanghai"])

    ip_loss     = sum(bw_to_gbps(c["bandwidth"]) for c in result_circuits if c["type"] == "IP" and c["is_broken"])
    ip_loss_sh  = sum(bw_to_gbps(c["bandwidth"]) for c in result_circuits
                      if c["type"] == "IP" and c["is_broken"] and c["is_shanghai"])

    return {
        "broken_ids": list(broken_ids),
        "circuits": result_circuits,
        "summary": {
            "iepl_total":      iepl_total,
            "iepl_broken":     iepl_broken,
            "iepl_broken_sh":  iepl_broken_sh,
            "ip_loss_gbps":    round(ip_loss, 4),
            "ip_loss_sh_gbps": round(ip_loss_sh, 4),
        },
    }
