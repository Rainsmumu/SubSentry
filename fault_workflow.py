"""故障事件的五阶段流程、字段和渠道完成状态。"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime


STAGES = [
    {
        "id": "first_report",
        "label": "首报",
        "channels": [
            ("phone", "电话传报"),
            ("email", "邮件传报"),
            ("sms", "短信传报"),
            ("supervisor_excel", "专业主管文件"),
        ],
        "required_fields": ["complaint_count"],
    },
    {
        "id": "impact_report",
        "label": "业务影响情况传报",
        "channels": [
            ("email_attachment", "邮件及附件"),
            ("wechat", "微信传报"),
        ],
        "required_fields": [],
    },
    {
        "id": "breakpoint_report",
        "label": "断点续报",
        "channels": [
            ("email", "邮件传报"),
            ("sms", "短信传报"),
            ("supervisor_excel", "专业主管文件"),
        ],
        "required_fields": ["distance_km", "complaint_count"],
    },
    {
        "id": "repair_plan_report",
        "label": "维修计划续报",
        "channels": [
            ("email", "邮件传报"),
            ("sms", "短信传报"),
            ("supervisor_excel", "专业主管文件"),
        ],
        "required_fields": [
            "repair_start_date", "expected_restore_date", "complaint_count"
        ],
    },
    {
        "id": "final_report",
        "label": "终报",
        "channels": [
            ("email", "邮件传报"),
            ("sms", "短信传报"),
            ("supervisor_excel", "专业主管文件"),
        ],
        "required_fields": ["actual_restore_time", "fault_cause", "complaint_count"],
    },
]

STAGE_BY_ID = {stage["id"]: stage for stage in STAGES}

DEFAULT_FIELDS = {
    "first_report": {"complaint_count": ""},
    "impact_report": {},
    "breakpoint_report": {"distance_km": "", "complaint_count": "0"},
    "repair_plan_report": {
        "repair_start_date": "",
        "expected_restore_date": "",
        "complaint_count": "0",
    },
    "final_report": {
        "actual_restore_time": "",
        "fault_cause": "",
        "complaint_count": "0",
    },
}


def applicable_stage_ids(cable: dict) -> list[str]:
    if cable.get("workflow_type") == "nanhui_impact_only":
        return ["impact_report"]
    return [stage["id"] for stage in STAGES]


def ensure_event_workflow(event: dict) -> dict:
    """补齐旧事件缺少的流程结构，保留已有字段和完成记录。"""
    workflow = event.setdefault("workflow", {})
    fields = workflow.setdefault("fields", {})
    tasks = workflow.setdefault("tasks", {})

    for stage in STAGES:
        stage_id = stage["id"]
        stage_fields = fields.setdefault(stage_id, {})
        for key, value in DEFAULT_FIELDS[stage_id].items():
            stage_fields.setdefault(key, value)

        stage_tasks = tasks.setdefault(stage_id, {})
        for channel_id, _ in stage["channels"]:
            stage_tasks.setdefault(channel_id, {
                "completed": False,
                "completed_at": "",
            })
    return event


def _has_value(value) -> bool:
    return value is not None and str(value).strip() != ""


def stage_ready(event: dict, stage_id: str) -> bool:
    ensure_event_workflow(event)
    stage = STAGE_BY_ID[stage_id]
    fields = event["workflow"]["fields"][stage_id]
    return all(_has_value(fields.get(key)) for key in stage["required_fields"])


def stage_completed(event: dict, stage_id: str) -> bool:
    ensure_event_workflow(event)
    tasks = event["workflow"]["tasks"][stage_id]
    return bool(tasks) and all(item.get("completed", False) for item in tasks.values())


def event_resolved_at(event: dict) -> str:
    """终报全部渠道完成时间；未完成终报时返回空字符串。"""
    if not stage_completed(event, "final_report"):
        return ""
    tasks = event["workflow"]["tasks"]["final_report"].values()
    times = [item.get("completed_at", "") for item in tasks if item.get("completed_at")]
    return max(times) if times else event["workflow"]["fields"]["final_report"].get(
        "actual_restore_time", ""
    )


def _previous_applicable_completed(event: dict, cable: dict, stage_id: str) -> bool:
    applicable = applicable_stage_ids(cable)
    index = applicable.index(stage_id)
    return all(stage_completed(event, previous) for previous in applicable[:index])


def workflow_view(event: dict, cable: dict) -> dict:
    ensure_event_workflow(event)
    applicable = applicable_stage_ids(cable)
    stage_views = []
    completed_count = 0

    for stage in STAGES:
        stage_id = stage["id"]
        is_applicable = stage_id in applicable
        ready = stage_ready(event, stage_id)
        complete = is_applicable and stage_completed(event, stage_id)
        previous_complete = is_applicable and _previous_applicable_completed(
            event, cable, stage_id
        )
        tasks = event["workflow"]["tasks"][stage_id]
        any_task = any(item.get("completed", False) for item in tasks.values())
        field_values = event["workflow"]["fields"][stage_id]
        any_field = any(_has_value(value) and str(value) != "0" for value in field_values.values())

        if not is_applicable:
            status = "not_applicable"
        elif complete:
            status = "completed"
            completed_count += 1
        elif not ready and stage["required_fields"]:
            status = "in_progress" if any_task or any_field else "waiting"
        elif any_task:
            status = "in_progress"
        else:
            status = "not_started"

        stage_views.append({
            "id": stage_id,
            "label": stage["label"],
            "applicable": is_applicable,
            "ready": ready,
            "previous_complete": previous_complete,
            "can_complete": ready and previous_complete,
            "status": status,
            "fields": deepcopy(field_values),
            "tasks": [
                {
                    "id": channel_id,
                    "label": channel_label,
                    **deepcopy(tasks[channel_id]),
                }
                for channel_id, channel_label in stage["channels"]
            ],
        })

    total = len(applicable)
    return {
        "type": cable.get("workflow_type"),
        "stages": stage_views,
        "completed_count": completed_count,
        "total_count": total,
        "progress_percent": round(completed_count * 100 / total) if total else 0,
        "resolved": bool(event_resolved_at(event)),
        "resolved_at": event_resolved_at(event),
    }


def update_stage_fields(event: dict, stage_id: str, values: dict) -> None:
    if stage_id not in STAGE_BY_ID:
        raise ValueError("无效的传报阶段")
    ensure_event_workflow(event)
    # 旧版本可能已完成渠道确认，但尚不存在后来新增的必填字段；允许补录一次。
    if stage_completed(event, stage_id) and stage_ready(event, stage_id):
        raise ValueError("该阶段已经完成，历史传报内容已锁定")
    allowed = set(DEFAULT_FIELDS[stage_id])
    fields = event["workflow"]["fields"][stage_id]

    for key, value in values.items():
        if key not in allowed:
            continue
        text = str(value or "").strip()
        if key == "complaint_count":
            try:
                count = int(text)
            except ValueError as exc:
                raise ValueError("用户申告数必须是非负整数") from exc
            if count < 0:
                raise ValueError("用户申告数不能小于0")
            text = str(count)
        if key == "distance_km" and text:
            try:
                if float(text) < 0:
                    raise ValueError
            except ValueError as exc:
                raise ValueError("断点距离必须是非负数字") from exc
        fields[key] = text


def set_task_completed(
    event: dict, cable: dict, stage_id: str, channel_id: str, completed: bool
) -> None:
    if stage_id not in applicable_stage_ids(cable):
        raise ValueError("该海缆不适用此传报阶段")
    stage = STAGE_BY_ID.get(stage_id)
    if not stage or channel_id not in dict(stage["channels"]):
        raise ValueError("无效的传报渠道")
    ensure_event_workflow(event)

    if completed:
        if not stage_ready(event, stage_id):
            raise ValueError("请先填写本阶段所需信息")
        if not _previous_applicable_completed(event, cable, stage_id):
            raise ValueError("请先完成前一个传报阶段")
    else:
        applicable = applicable_stage_ids(cable)
        stage_index = applicable.index(stage_id)
        for later_stage in applicable[stage_index + 1:]:
            later_tasks = event["workflow"]["tasks"][later_stage].values()
            if any(item.get("completed", False) for item in later_tasks):
                raise ValueError("后续阶段已有完成记录，不能取消当前阶段")

    task = event["workflow"]["tasks"][stage_id][channel_id]
    task["completed"] = bool(completed)
    task["completed_at"] = (
        datetime.now().isoformat(timespec="seconds") if completed else ""
    )
