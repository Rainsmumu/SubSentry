"""
cable_config.py — 海缆段落硬编码配置

包含上海国际局负责的 8 条海缆段落的所有静态信息，
以及路由字段关键字匹配规则（用于从电路表中识别哪些路由属于哪条段落）。
"""

from __future__ import annotations

# 8 条海缆段落配置
# id: 系统内唯一标识符
# cable: 海缆名称（通报中使用）
# segment: 段落编号（通报中使用）
# landing: 登陆站（崇明 / 南汇）
# route_desc: 路由描述（通报中"XX-XX"部分）
# direction: 影响方向（通报中"影响XX、XX方向"）
# match_all: 路由字段中必须同时包含的关键字列表（全部作为子串命中才算此段落）
#   兼容拼接海缆与空格/大小写差异，例如 "APCN2 S4A+PC1崇明" 命中 APCN2 S4A。
CABLES = [
    {
        "id": "TPE_S1S",
        "cable": "TPE",
        "segment": "S1S",
        "landing": "崇明",
        "route_desc": "崇明-BU1",
        "direction": "日本、美国",
        "match_all": ["TPE", "S1S"],
    },
    {
        "id": "TPE_S4",
        "cable": "TPE",
        "segment": "S4",
        "landing": "崇明",
        "route_desc": "崇明-淡水",
        "direction": "台湾、日本",
        "match_all": ["TPE", "S4"],
    },
    {
        "id": "APCN2_S3",
        "cable": "APCN2",
        "segment": "S3",
        "landing": "崇明",
        "route_desc": "崇明-香港",
        "direction": "香港、美国",
        "match_all": ["APCN2", "S3"],
    },
    {
        "id": "APCN2_S4A",
        "cable": "APCN2",
        "segment": "S4A",
        "landing": "崇明",
        "route_desc": "崇明-BU1",
        "direction": "韩国、日本",
        "match_all": ["APCN2", "S4A"],
    },
    {
        "id": "APG_S3",
        "cable": "APG",
        "segment": "S3",
        "landing": "崇明",
        "route_desc": "崇明-BU2",
        "direction": "韩国、日本",
        "match_all": ["APG", "S3"],
    },
    {
        "id": "NCP_S1_1",
        "cable": "NCP",
        "segment": "S1.1",
        "landing": "崇明",
        "route_desc": "崇明-BU1",
        "direction": "日本、美国",
        "match_all": ["NCP", "S1.1"],
    },
    {
        "id": "APG_S4",
        "cable": "APG",
        "segment": "S4",
        "landing": "南汇",
        "route_desc": "南汇-BU3",
        "direction": "日本、新加坡",
        "match_all": ["APG", "S4"],
    },
    {
        "id": "NCP_S3",
        "cable": "NCP",
        "segment": "S3",
        "landing": "南汇",
        "route_desc": "南汇-BU1",
        "direction": "日本、美国",
        "match_all": ["NCP", "S3"],
    },
]

# 索引：按 id 快速查找
CABLE_BY_ID = {c["id"]: c for c in CABLES}

# 说明：新版槽路表已把 "APCN2崇明"、"TPE崇明" 等模糊写法拆成明确段落
#（如 "APCN2 S4A"、"TPE S1S"），因此不再需要"疑似"匹配逻辑。


def get_cable_display_name(cable_id: str) -> str:
    """返回通报中使用的海缆显示名，如 'TPE海缆S4段'"""
    c = CABLE_BY_ID.get(cable_id)
    if not c:
        return cable_id
    return f"{c['cable']}海缆{c['segment']}段"


def _normalize_route(route_str: str) -> str:
    """归一化路由字段：转大写并去除所有空白，兼容空格/大小写差异。"""
    return "".join(str(route_str).upper().split())


def match_route_to_cable_ids(route_str: str) -> list[str]:
    """
    判断一个路由字段值命中了哪些海缆段落，返回所有命中段落 id 列表。

    采用"关键字全部为子串"匹配，兼容：
      - 拼接海缆："APCN2 S4A+PC1崇明" → ["APCN2_S4A"]
      - 空格/大小写差异："apcn2  s4a" → ["APCN2_S4A"]
      - "S1.1 段" 等后缀
    """
    if not route_str:
        return []

    norm = _normalize_route(route_str)
    matched = []
    for cable in CABLES:
        if all(_normalize_route(kw) in norm for kw in cable["match_all"]):
            matched.append(cable["id"])
    return matched


def match_route_to_cable(route_str: str) -> str | None:
    """返回路由字段命中的第一条海缆段落 id（无则 None）。保留供单值场景使用。"""
    ids = match_route_to_cable_ids(route_str)
    return ids[0] if ids else None
