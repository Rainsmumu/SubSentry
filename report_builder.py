"""根据故障事件变量生成首报、影响传报、续报和终报文案。"""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime

from cable_config import CABLE_BY_ID
from circuit_analyzer import format_gbps
from fault_workflow import ensure_event_workflow


def _parse_time(value: str) -> datetime:
    for fmt in (
        "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d", "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(str(value).strip(), fmt)
        except ValueError:
            pass
    raise ValueError(f"无法解析时间格式：{value}")


def _month_day(value: str, placeholder: str = "XX月XX日") -> str:
    if not value:
        return placeholder
    dt = _parse_time(value)
    return f"{dt.month}月{dt.day}日"


def _full_date(value: str, placeholder: str = "XXXX年XX月XX日") -> str:
    if not value:
        return placeholder
    dt = _parse_time(value)
    return f"{dt.year}年{dt.month}月{dt.day}日"


def _group_wechat_details(circuits: list[dict]) -> str:
    """同客户、方向和单条带宽合并，标题数量仍由原始电路条数计算。"""
    grouped = OrderedDict()
    for circuit in circuits:
        key = (
            circuit.get("customer", "") or "未注明客户",
            circuit.get("site_a", "") or "未注明",
            circuit.get("site_b", "") or "未注明",
            circuit.get("bandwidth", "") or "未注明",
        )
        grouped[key] = grouped.get(key, 0) + 1

    lines = []
    for (customer, site_a, site_b, bandwidth), count in grouped.items():
        display_bandwidth = f"{count}*{bandwidth}" if count > 1 else bandwidth
        lines.append(f"- {customer}：{site_a}-{site_b} {display_bandwidth}")
    return "\n".join(lines) if lines else "无"


def build_reports(
    cable_id: str,
    fault_time: str,
    summary: dict,
    broken_customer_circuits: list[dict],
    event: dict | None = None,
) -> dict:
    """生成五阶段文案；event 为空时兼容旧调用并使用待填写占位符。"""
    event = event or {"cable_id": cable_id, "fault_time": fault_time}
    ensure_event_workflow(event)
    fields = event["workflow"]["fields"]
    cable = CABLE_BY_ID.get(cable_id)
    if not cable:
        raise ValueError(f"未知海缆 id：{cable_id}")
    dt = _parse_time(fault_time)

    cable_name = cable["cable"]
    segment = cable["segment"]
    landing = cable["landing"]
    route_desc = cable["route_desc"]
    direction = cable["direction"]
    noc = cable["noc"]
    month_day = f"{dt.month}月{dt.day}日"
    hhmm = dt.strftime("%H:%M")

    responsible = cable["responsible"]
    first_phone = (
        "电话联系：\n"
        "1. 集团监控：01066073715\n"
        f"2. 三级经理{responsible['name']}：{responsible['phone']}\n\n"
        "传报内容：\n"
        f"{dt.hour}时{dt.minute:02d}分，{cable_name}海缆{segment}段中断。"
    )
    first_email_subject = (
        f"{month_day}{cable_name}海缆{segment}段（{route_desc}）中断"
    )
    first_email_body = (
        f"经与{landing}登陆站确认，{month_day}{hhmm}，"
        f"{cable_name}海缆{segment}段（{route_desc}）中断，"
        f"影响{direction}方向业务电路，具体清单整理中。"
    )
    first_email = f"标题：{first_email_subject}\n\n正文：\n{first_email_body}"
    first_sms = (
        f"网络运营重要情况传报（C1+故障）：{month_day}{hhmm} "
        f"{cable_name}海缆{segment}段{landing}出口发生故障，"
        f"业务影响正在统计中，故障位置待{noc}定位，已上报集团，"
        f"基础设施运营中心正在处理中。"
    )

    impact_email = (
        f"关于{month_day}{cable_name}海缆{segment}段方向中断，"
        f"影响{direction}方向业务电路，具体影响清单见附件。"
    )
    detail_text = _group_wechat_details(broken_customer_circuits)
    impact_wechat = (
        f"{month_day}{hhmm}，{cable_name}海缆{segment}段{landing}出口中断，受影响情况：\n"
        f"1）IP损失{format_gbps(summary['ip_loss_gbps'])}带宽，其中上海落地"
        f"{format_gbps(summary['ip_loss_sh_gbps'])}。\n"
        f"2）{summary['iepl_broken']}条客户专线中断，其中上海落地"
        f"{summary['iepl_broken_sh']}条，具体为：\n\n{detail_text}"
    )

    distance = fields["breakpoint_report"].get("distance_km") or "XX"
    breakpoint_email = (
        f"{month_day}，{cable_name}海缆{segment}段中断，经{noc}定位，"
        f"断点距离{landing}登陆站{distance}公里。"
    )
    breakpoint_sms = (
        f"网络运营重要情况补充传报（C1+故障）：{month_day} "
        f"{cable_name}海缆{segment}段中断，经{noc}定位，"
        f"断点距离{landing}登陆站{distance}公里。"
    )

    repair_fields = fields["repair_plan_report"]
    repair_start = _full_date(repair_fields.get("repair_start_date", ""))
    expected_restore = _month_day(repair_fields.get("expected_restore_date", ""))
    repair_email = (
        f"{month_day}，{cable_name}海缆{segment}段中断，计划于{repair_start}开始维修，"
        f"预计{expected_restore}修复。"
    )
    repair_sms = (
        f"网络运营重要情况补充传报（C1+故障）：{month_day} "
        f"{cable_name}海缆{segment}段（{route_desc}）方向中断，计划于"
        f"{repair_start}开始维修，预计{expected_restore}修复。"
    )

    final_fields = fields["final_report"]
    actual_restore = _full_date(final_fields.get("actual_restore_time", ""))
    final_email = (
        f"{month_day}，{cable_name}海缆{segment}段（{route_desc}）方向中断，"
        f"经{landing}登陆站确认，已于{actual_restore}修复。"
    )
    final_sms = (
        f"网络运营重要情况补充传报（C1+故障）：{month_day} "
        f"{cable_name}海缆{segment}段（{route_desc}）方向中断，"
        f"经{landing}登陆站确认，已于{actual_restore}修复。"
    )

    stages = {
        "first_report": {"phone": first_phone, "email": first_email, "sms": first_sms},
        "impact_report": {"email_attachment": impact_email, "wechat": impact_wechat},
        "breakpoint_report": {"email": breakpoint_email, "sms": breakpoint_sms},
        "repair_plan_report": {"email": repair_email, "sms": repair_sms},
        "final_report": {"email": final_email, "sms": final_sms},
    }

    # 保留旧字段，避免旧页面或外部调用在前端升级期间失效。
    return {
        "stages": stages,
        "first_email": first_email,
        "first_sms": first_sms,
        "follow_email": impact_email,
        "follow_wechat": impact_wechat,
    }
