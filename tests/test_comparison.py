import unittest
from unittest.mock import patch

import comparison


class ComparisonScopeTests(unittest.TestCase):
    @patch("comparison.build_source_index", return_value={})
    @patch("comparison.load_manual")
    @patch("comparison.analyze")
    @patch("comparison.manual_file_for", return_value="manual.xlsx")
    def test_ip_circuits_are_reported_but_not_marked_system_only(
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
        self.assertEqual(result["summary"]["ip_excluded"], 1)
        self.assertEqual(result["system_only"], [])


if __name__ == "__main__":
    unittest.main()
