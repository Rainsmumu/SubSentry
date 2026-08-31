import unittest

from cable_config import CABLE_BY_ID
from fault_workflow import (
    ensure_event_workflow,
    event_resolved_at,
    set_task_completed,
    update_stage_fields,
    workflow_view,
)


class FaultWorkflowTests(unittest.TestCase):
    def _event(self, cable_id="TPE_S4"):
        event = {
            "id": "event-1",
            "cable_id": cable_id,
            "fault_time": "2026-08-30T14:37",
            "created_at": "2026-08-30T14:38:00",
        }
        return ensure_event_workflow(event)

    def test_nanhui_only_has_impact_stage(self):
        event = self._event("APG_S4")
        view = workflow_view(event, CABLE_BY_ID["APG_S4"])

        applicable = [stage["id"] for stage in view["stages"] if stage["applicable"]]
        self.assertEqual(applicable, ["impact_report"])
        self.assertEqual(view["total_count"], 1)

    def test_stage_completion_follows_fixed_order(self):
        event = self._event()
        cable = CABLE_BY_ID["TPE_S4"]

        with self.assertRaisesRegex(ValueError, "前一个"):
            set_task_completed(event, cable, "impact_report", "wechat", True)

        update_stage_fields(event, "first_report", {"complaint_count": "1"})
        for channel in ("phone", "email", "sms", "supervisor_excel"):
            set_task_completed(event, cable, "first_report", channel, True)
        set_task_completed(event, cable, "impact_report", "email_attachment", True)
        set_task_completed(event, cable, "impact_report", "wechat", True)

        view = workflow_view(event, cable)
        self.assertEqual(view["completed_count"], 2)
        self.assertEqual(view["progress_percent"], 40)

    def test_final_completion_resolves_without_deleting_event(self):
        event = self._event()
        cable = CABLE_BY_ID["TPE_S4"]

        update_stage_fields(event, "first_report", {"complaint_count": "1"})
        update_stage_fields(event, "breakpoint_report", {
            "distance_km": "126.4", "complaint_count": "2",
        })
        update_stage_fields(event, "repair_plan_report", {
            "repair_start_date": "2026-09-02",
            "expected_restore_date": "2026-09-04",
            "complaint_count": "3",
        })
        update_stage_fields(event, "final_report", {
            "actual_restore_time": "2026-09-03T22:18",
            "fault_cause": "外力损伤",
            "complaint_count": "3",
        })
        for stage_id, channels in (
            ("first_report", ("phone", "email", "sms", "supervisor_excel")),
            ("impact_report", ("email_attachment", "wechat")),
            ("breakpoint_report", ("email", "sms", "supervisor_excel")),
            ("repair_plan_report", ("email", "sms", "supervisor_excel")),
            ("final_report", ("email", "sms", "supervisor_excel")),
        ):
            for channel in channels:
                set_task_completed(event, cable, stage_id, channel, True)

        self.assertTrue(event_resolved_at(event))
        self.assertTrue(workflow_view(event, cable)["resolved"])

        with self.assertRaisesRegex(ValueError, "已锁定"):
            update_stage_fields(event, "final_report", {"fault_cause": "修改后的原因"})

    def test_completed_earlier_stage_cannot_be_reopened_after_later_progress(self):
        event = self._event()
        cable = CABLE_BY_ID["TPE_S4"]
        update_stage_fields(event, "first_report", {"complaint_count": "1"})
        for channel in ("phone", "email", "sms", "supervisor_excel"):
            set_task_completed(event, cable, "first_report", channel, True)
        set_task_completed(event, cable, "impact_report", "email_attachment", True)

        with self.assertRaisesRegex(ValueError, "后续阶段"):
            set_task_completed(event, cable, "first_report", "email", False)

    def test_first_report_requires_saved_complaint_count(self):
        event = self._event()
        cable = CABLE_BY_ID["TPE_S4"]

        self.assertFalse(workflow_view(event, cable)["stages"][0]["ready"])
        with self.assertRaisesRegex(ValueError, "所需信息"):
            set_task_completed(event, cable, "first_report", "phone", True)

        update_stage_fields(event, "first_report", {"complaint_count": "0"})
        self.assertTrue(workflow_view(event, cable)["stages"][0]["ready"])

    def test_legacy_completed_stage_can_fill_new_required_field_once(self):
        event = self._event()
        for task in event["workflow"]["tasks"]["first_report"].values():
            task["completed"] = True

        update_stage_fields(event, "first_report", {"complaint_count": "2"})
        self.assertEqual(
            event["workflow"]["fields"]["first_report"]["complaint_count"], "2"
        )
        with self.assertRaisesRegex(ValueError, "已锁定"):
            update_stage_fields(event, "first_report", {"complaint_count": "3"})


if __name__ == "__main__":
    unittest.main()
