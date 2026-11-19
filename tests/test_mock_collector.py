import unittest

from blogger_crawler.mock_collector import collect_mock_snapshot
from blogger_crawler.models import Blogger


class MockCollectorTest(unittest.TestCase):
    def test_generates_stable_success_snapshot(self):
        blogger = Blogger(red_id="test_001", nickname="测试A")

        first = collect_mock_snapshot(blogger, "2026-07")
        second = collect_mock_snapshot(blogger, "2026-07")

        self.assertEqual(first.red_id, "test_001")
        self.assertEqual(first.nickname, "测试A")
        self.assertEqual(first.crawl_month, "2026-07")
        self.assertEqual(first.crawl_status, "success")
        self.assertEqual(first.fans_count, second.fans_count)
        self.assertGreater(first.note_count_30d, 0)
        self.assertGreater(first.exposure_median_30d, 0)


if __name__ == "__main__":
    unittest.main()
