import unittest

from cable_config import match_route_to_cable_ids


class CableRouteMatchingTests(unittest.TestCase):
    def test_composite_route_keeps_cable_and_segment_paired(self):
        matched = set(match_route_to_cable_ids("NCP S3+APG S4"))

        self.assertEqual(matched, {"NCP_S3", "APG_S4"})
        self.assertNotIn("APG_S3", matched)

    def test_composite_route_without_spaces_is_supported(self):
        matched = set(match_route_to_cable_ids("NCPS3+APGS4"))

        self.assertEqual(matched, {"NCP_S3", "APG_S4"})

    def test_single_known_part_in_composite_route_is_matched(self):
        self.assertEqual(
            match_route_to_cable_ids("APCN2 S4A+PC1崇明"),
            ["APCN2_S4A"],
        )

    def test_longer_segment_numbers_do_not_match_shorter_segments(self):
        self.assertNotIn("APG_S3", match_route_to_cable_ids("APG S30"))
        self.assertNotIn("NCP_S1_1", match_route_to_cable_ids("NCP S1.10"))


if __name__ == "__main__":
    unittest.main()
