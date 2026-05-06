"""
report_builder.py — 通报文本生成

严格按照《业务背景说明》第 4、5 节的模板格式填充四段通报：
  - 首报邮件
  - 首报短信
  - 续报邮件
  - 续报微信
"""

from __future__ import annotations

from datetime import datetime
from cable_config import CABLE_BY_ID
from circuit_analyzer import format_gbps


def _parse_fault_time(fault_time: str) -> datetime:
    """解析故障时间字符串，支持 'YYYY-MM-DDTHH:MM' 和 'YYYY-MM-DD HH:MM' 格式。"""
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(fault_time.strip(), fmt)
        except ValueError:
            pass
    raise ValueError(f"无法解析故障时间格式：{fault_time}")


def build_reports(
    cable_id: str,
    fault_time: str,
    summary: dict,
    broken_iepl_sh: list[dict],
) -> dict[str, str]:
    """
    生成四段通报文本。

    cable_id:      故障海缆段落 id（如 "TPE_S4"）
    fault_time:    故障时间字符串（如 "2025-12-21T04:24"）
    summary:       circuit_analyzer.analyze() 返回的 summary 字典
    broken_iepl_sh: 上海落地且业务中断的 IEPL 电路列表（用于微信明细）

    返回 dict：
      {
        "first_email": str,
        "first_sms":   str,
        "follow_email":str,
        "follow_wechat":str,
      }
    """
    cable = CABLE_BY_ID.get(cable_id)
    if not cable:
        raise ValueError(f"未知海缆 id：{cable_id}")

    dt = _parse_fault_time(fault_time)
    month  = dt.month
    day    = dt.day
    hhmm   = dt.strftime("%H:%M")

    cable_name   = cable["cable"]        # 如 "TPE"
    segment      = cable["segment"]      # 如 "S4"
    landing      = cable["landing"]      # 如 "崇明"
    route_desc   = cable["route_desc"]   # 如 "崇明-淡水"
    direction    = cable["direction"]    # 如 "台湾、日本"

    # ── 首报邮件 ─────────────────────────────────────────────────────
    # 模板：经与XX登陆站确认，XX月XX日XX:XX XX海缆XX段（XX-XX）中断，
    #        影响XX、XX方向业务电路，具体清单整理中。
    first_email = (
        f"经与{landing}登陆站确认，"
        f"{month}月{day}日{hhmm} "
        f"{cable_name}海缆{segment}段（{route_desc}）中断，"
        f"影响{direction}方向业务电路，具体清单整理中。"
    )

    # ── 首报短信 ─────────────────────────────────────────────────────
    # 模板：网络运营重要情况传报(C1+故障)：XX月XX日XX:XX ，
    #        XX海缆XX段XX出口发生故障，业务影响正在统计中，
    #        故障位置待NOC定位，已上报集团，基础设施运营中心正在处理中。
    first_sms = (
        f"网络运营重要情况传报(C1+故障)："
        f"{month}月{day}日{hhmm}，"
        f"{cable_name}海缆{segment}段{landing}出口发生故障，"
        f"业务影响正在统计中，故障位置待NOC定位，"
        f"已上报集团，基础设施运营中心正在处理中。"
    )

    # ── 续报邮件 ─────────────────────────────────────────────────────
    # 模板：关于XX月XX日 XX海缆XX段方向中断，
    #        影响XX、XX方向业务电路，具体影响清单见附件。
    follow_email = (
        f"关于{month}月{day}日 "
        f"{cable_name}海缆{segment}段方向中断，"
        f"影响{direction}方向业务电路，具体影响清单见附件。"
    )

    # ── 续报微信 ─────────────────────────────────────────────────────
    # 模板：XX月XX日XX:XX  XX海缆XX段XX出口中断，受影响情况：
    # 1）IP损失XXG带宽，其中上海落地XXG。
    # 2）XX条客户专线中断，其中上海落地XX条，具体为XX。
    ip_total    = format_gbps(summary["ip_loss_gbps"])
    ip_sh       = format_gbps(summary["ip_loss_sh_gbps"])
    iepl_broken = summary["iepl_broken"]
    iepl_sh     = summary["iepl_broken_sh"]

    # 微信明细：上海落地中断 IEPL，格式"- 客户名：A端-B端 带宽"
    detail_lines = []
    for c in broken_iepl_sh:
        line = f"   - {c['customer']}：{c['site_a']}-{c['site_b']} {c['bandwidth']}"
        # 如果是临时路由，添加标注
        if c.get("is_temp_route", False):
            line += " ⚠️临时路由"
        detail_lines.append(line)
    detail_str = "\n" + "\n".join(detail_lines) if detail_lines else "无"

    follow_wechat = (
        f"{month}月{day}日{hhmm}  "
        f"{cable_name}海缆{segment}段{landing}出口中断，受影响情况：\n"
        f"1）IP损失{ip_total}带宽，其中上海落地{ip_sh}。\n"
        f"2）{iepl_broken}条客户专线中断，其中上海落地{iepl_sh}条，具体为：{detail_str}"
    )

    return {
        "first_email":   first_email,
        "first_sms":     first_sms,
        "follow_email":  follow_email,
        "follow_wechat": follow_wechat,
    }
