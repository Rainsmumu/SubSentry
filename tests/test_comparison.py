import unittest
from unittest.mock import patch

import comparison


class ComparisonScopeTests(unittest.TestCase):
    @patch("comparison.build_source_index", return_value={})
    @patch("comparison.load_manual")
    @patch("comparison.analyze")
    @patch("comparison.manual_file_for", return_value="manual.xlsx")
    def test_ip_circuits_without_manual_reference_are_unverified(
        self, _manual_file, analyze_mock, load_manual_mock, _source_index
    ):
        iepl = {
            "circuit_id": "SHI/CU-TOK/CU EP001",
            "customer": "测试客户",
            "site_a": "上海",
            "site_b": "日本",
            "bandwidth": "1G",
            "impact_status": "无保护",
            "type": "IEPL",
            "route1": "TPE S1S",
        }
        ip = {
            "circuit_id": "SHI/CU-TOK/CU GE10L001",
            "customer": "IP中继",
            "site_a": "上海",
            "site_b": "日本",
            "bandwidth": "10G",
            "impact_status": "无保护",
            "type": "IP",
            "route1": "TPE S1S",
        }
        analyze_mock.return_value = {"circuits": [iepl, ip]}
        load_manual_mock.return_value = [{
            "status": "中断",
            "circuit_id": iepl["circuit_id"],
            "customer": iepl["customer"],
            "site_a": iepl["site_a"],
            "site_b": iepl["site_b"],
            "bandwidth": iepl["bandwidth"],
            "routes": [iepl["route1"]],
        }]

        result = comparison.compare("TPE_S1S")

        self.assertEqual(result["summary"]["matched"], 1)
        self.assertEqual(result["summary"]["system_only"], 0)
        self.assertEqual(result["summary"]["unverified"], 1)
        self.assertEqual(result["system_only"], [])
        self.assertEqual(result["unverified"][0]["circuit_id"], ip["circuit_id"])

    def test_ip_circuits_use_normal_diff_when_manual_ip_reference_exists(self):
        matched_ip = {
            "circuit_id": "SHI/CU-TOK/CU GE10L001",
            "customer": "IP中继一",
            "site_a": "上海",
            "site_b": "日本",
            "bandwidth": "10G",
            "impact_status": "无保护",
            "type": "IP",
            "route1": "TPE S1S",
        }
        extra_ip = {
            **matched_ip,
            "circuit_id": "SHI/CU-TOK/CU GE10L002",
            "customer": "IP中继二",
        }
        manual = [{
            "status": "中断",
            "circuit_id": matched_ip["circuit_id"],
            "customer": matched_ip["customer"],
            "site_a": matched_ip["site_a"],
            "site_b": matched_ip["site_b"],
            "bandwidth": matched_ip["bandwidth"],
            "routes": [matched_ip["route1"]],
        }]
        source_index = {
            "SHI/CU-TOK/CUGE10L001": [{"type": "IP"}],
        }

        with (
            patch("comparison.manual_file_for", return_value="manual.xlsx"),
            patch("comparison.analyze", return_value={"circuits": [matched_ip, extra_ip]}),
            patch("comparison.load_manual", return_value=manual),
            patch("comparison.build_source_index", return_value=source_index),
        ):
            result = comparison.compare("TPE_S1S")

        self.assertEqual(result["summary"]["matched"], 1)
        self.assertEqual(result["summary"]["system_only"], 1)
        self.assertEqual(result["summary"]["unverified"], 0)
        self.assertEqual(result["system_only"][0]["circuit_id"], extra_ip["circuit_id"])


if __name__ == "__main__":
    unittest.main()
