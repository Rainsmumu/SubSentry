"""
cable_config.py — 海缆段落硬编码配置

包含上海国际局负责的 8 条海缆段落的所有静态信息，
以及路由字段关键字匹配规则（用于从电路表中识别哪些路由属于哪条段落）。
"""

# 8 条海缆段落配置
# id: 系统内唯一标识符
# cable: 海缆名称（通报中使用）
# segment: 段落编号（通报中使用）
# landing: 登陆站（崇明 / 南汇）
# route_desc: 路由描述（通报中"XX-XX"部分）
# direction: 影响方向（通报中"影响XX、XX方向"）
# match_all: 路由字段中必须同时包含的关键字列表（全部匹配才算此段落）
# match_ambiguous: 路由字段写法模糊时（无法区分段落），如果命中这些关键字则标记为"疑似"
#   key: 模糊关键字组合，value: 可能是哪些 segment id
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

# 模糊写法 → 可能对应的段落 id 列表
# 当路由字段写法无法区分具体段落时，命中这里的规则会标注"疑似"
AMBIGUOUS_PATTERNS = [
    {
        # "APCN2崇明" / "崇明APCN2" 等：无法区分 S3 和 S4A
        "keywords": ["APCN2", "崇明"],
        "possible_ids": ["APCN2_S3", "APCN2_S4A"],
    },
    {
        # "TPE崇明" / "崇明TPE" 等：无法区分 S1S 和 S4
        "keywords": ["TPE", "崇明"],
        "possible_ids": ["TPE_S1S", "TPE_S4"],
    },
]

# 索引：按 id 快速查找
CABLE_BY_ID = {c["id"]: c for c in CABLES}


def get_cable_display_name(cable_id: str) -> str:
    """返回通报中使用的海缆显示名，如 'TPE海缆S4段'"""
    c = CABLE_BY_ID.get(cable_id)
    if not c:
        return cable_id
    return f"{c['cable']}海缆{c['segment']}段"


def match_route_to_cable(route_str: str) -> tuple[str | None, bool]:
    """
    判断一个路由字段值属于哪条海缆段落。

    返回 (cable_id, is_ambiguous)：
      - cable_id: 精确匹配到的段落 id，或 None
      - is_ambiguous: 是否命中模糊写法（True 时 cable_id 为 None）
    """
    if not route_str:
        return None, False

    upper = route_str.upper()

    # 优先尝试精确关键字匹配（按顺序，越具体越靠前）
    for cable in CABLES:
        if all(kw.upper() in upper for kw in cable["match_all"]):
            return cable["id"], False

    # 再检查模糊写法
    for pattern in AMBIGUOUS_PATTERNS:
        if all(kw.upper() in upper for kw in pattern["keywords"]):
            return None, True  # 模糊匹配，无法确定具体段落

    return None, False
