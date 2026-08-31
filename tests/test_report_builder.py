import unittest

from report_builder import build_reports


class ReportBuilderTests(unittest.TestCase):
    def test_full_stage_templates_and_wechat_grouping(self):
        event = {
            "cable_id": "TPE_S4",
            "fault_time": "2026-08-30T14:37",
            "workflow": {
                "fields": {
                    "breakpoint_report": {"distance_km": "126.4", "complaint_count": "2"},
                    "repair_plan_report": {
                        "repair_start_date": "2026-09-02",
                        "expected_restore_date": "2026-09-04",
                        "complaint_count": "3",
                    },
                    "final_report": {
                        "actual_restore_time": "2026-09-03T22:18",
                        "fault_cause": "外力损伤",
                        "complaint_count": "3",
                    },
                },
            },
        }
        summary = {
            "ip_loss_gbps": 13,
            "ip_loss_sh_gbps": 13,
            "iepl_broken": 3,
            "iepl_broken_sh": 2,
        }
        circuits = [
            {"customer": "中华电信", "site_a": "上海", "site_b": "美国", "bandwidth": "10G"},
            {"customer": "中华电信", "site_a": "上海", "site_b": "美国", "bandwidth": "10G"},
            {"customer": "测试客户", "site_a": "北京", "site_b": "日本", "bandwidth": "1G"},
        ]

        reports = build_reports("TPE_S4", event["fault_time"], summary, circuits, event)

        phone = reports["stages"]["first_report"]["phone"]
        self.assertIn("集团监控：01066073715", phone)
        self.assertIn("三级经理邹斌：18601723639", phone)
        self.assertIn("传报内容", phone)
        self.assertIn("中华电信：上海-美国 2*10G", reports["stages"]["impact_report"]["wechat"])
        self.assertIn("3条客户专线", reports["stages"]["impact_report"]["wechat"])
        self.assertIn("126.4公里", reports["stages"]["breakpoint_report"]["email"])
        self.assertIn("2026年9月2日", reports["stages"]["repair_plan_report"]["sms"])
        self.assertIn("2026年9月3日修复", reports["stages"]["final_report"]["email"])


if __name__ == "__main__":
    unittest.main()
