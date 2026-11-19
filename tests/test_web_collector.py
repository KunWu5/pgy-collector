import unittest
from decimal import Decimal
from pathlib import Path

from helpers import workspace_tempdir
from blogger_crawler.models import Blogger
from blogger_crawler.web_collector import (
    SessionExpired,
    SessionNotConfigured,
    parse_snapshot,
    parse_detail_metrics,
    prepare_search_page,
    find_detail_result_avatar,
    select_search_payload,
    select_detail_period,
    validate_session,
)


class CollectorTest(unittest.TestCase):
    def test_prepare_search_page_reports_session_expired_after_redirect(self):
        class EmptyLocator:
            def count(self):
                return 0

        class FakePage:
            def __init__(self):
                self.url = "https://example.com/search"

            def wait_for_timeout(self, milliseconds):
                self.url = "https://example.com/"

            def locator(self, selector):
                return EmptyLocator()

        with self.assertRaisesRegex(SessionExpired, "登录态已失效"):
            prepare_search_page(FakePage(), 30000)

    def test_prepare_search_page_waits_for_spa_ready_before_clicking_nickname_tab(self):
        class FakeLocator:
            def __init__(self, page):
                self.page = page

            def count(self):
                return 1

            @property
            def first(self):
                return self

            def click(self):
                self.page.clicked = True

        class FakePage:
            def __init__(self):
                self.waited_ms = 0
                self.clicked = False

            def wait_for_timeout(self, milliseconds):
                self.waited_ms = milliseconds

            def get_by_text(self, text, *, exact):
                return FakeLocator(self)

            def get_by_placeholder(self, placeholder):
                return object()

        page = FakePage()
        field = prepare_search_page(page, 30000)

        self.assertIsNotNone(field)
        self.assertGreaterEqual(page.waited_ms, 1000)
        self.assertTrue(page.clicked)

    def test_parse_search_response_maps_live_fields_without_fake_90_day_values(self):
        payload = {
            "success": True,
            "data": {
                "kols": [
                    {
                        "redId": "638355164",
                        "name": "Mao嗷嗷呢",
                        "fansNum": 243933,
                        "picturePrice": 29800.0,
                        "videoPrice": 29800.0,
                        "contentTags": [
                            {"taxonomy1Tag": "护肤", "taxonomy2Tags": ["面部保养"]}
                        ],
                        "featureTags": ["抗老", "美白"],
                        "coopNoteNum30d": 0,
                        "accumCommonImpMedinNum30d": 608702,
                        "clickMidNum": 43010,
                        "mEngagementNum": 4586,
                    }
                ]
            },
        }
        snapshot = parse_snapshot(payload, Blogger("638355164", "Mao嗷嗷呢"), "2026-07")

        self.assertEqual(snapshot.red_id, "638355164")
        self.assertEqual(snapshot.nickname, "Mao嗷嗷呢")
        self.assertEqual(snapshot.fans_count, 243933)
        self.assertEqual(snapshot.image_price, Decimal("29800.00"))
        self.assertEqual(snapshot.video_price, Decimal("29800.00"))
        self.assertEqual(snapshot.tags, ["护肤", "面部保养", "抗老", "美白"])
        self.assertEqual(snapshot.note_count_30d, 0)
        self.assertEqual(snapshot.exposure_median_30d, 608702)
        self.assertEqual(snapshot.read_median_30d, 43010)
        self.assertEqual(snapshot.interaction_median_30d, 4586)
        self.assertIsNone(snapshot.note_count_90d)
        self.assertEqual(snapshot.crawl_status, "success")

    def test_validate_session_requires_saved_session_file(self):
        with workspace_tempdir() as tmp:
            with self.assertRaisesRegex(SessionNotConfigured, "登录态"):
                validate_session(
                    {"session_path": ".session/session.json"},
                    Path(tmp),
                )

    def test_parse_detail_metrics_reads_cooperation_note_count_and_card_medians(self):
        payload = {
            "success": True,
            "data": {
                "noteNumber": 4,
                "impMedian": 451477,
                "readMedian": 39251,
                "interactionMedian": 4169,
                "mEngagementNum": 4311,
            },
        }

        metrics = parse_detail_metrics(payload)

        self.assertEqual(
            metrics,
            {
                "note_count": 4,
                "exposure_median": 451477,
                "read_median": 39251,
                "interaction_median": 4311,
            },
        )

    def test_select_detail_period_uses_the_cooperation_date_dropdown(self):
        class FakeLocator:
            def __init__(self, texts, clicks):
                self.texts = texts
                self.clicks = clicks

            def all_inner_texts(self):
                return self.texts

            def nth(self, index):
                return FakeLocator([self.texts[index]], self.clicks)

            def click(self, **kwargs):
                self.clicks.append(self.texts[0])

        class FakePage:
            def __init__(self):
                self.clicks = []
                self.selects = FakeLocator(
                    ["最新发布", "全部流量", "图文+视频", "近30日", "全流量", "近30日"],
                    self.clicks,
                )
                self.options = FakeLocator(
                    ["近30日", "近90日"],
                    self.clicks,
                )

            def locator(self, selector):
                if selector == ".d-select-wrapper":
                    return self.selects
                if selector == ".d-option-name":
                    return self.options
                raise AssertionError(selector)

        page = FakePage()

        select_detail_period(page, 90)

        self.assertEqual(page.clicks, ["近30日", "近90日"])

    def test_find_detail_result_avatar_uses_result_table_instead_of_nickname_text(self):
        class FakeRows:
            def count(self):
                return 1

            @property
            def first(self):
                return "result-row"

        class FakePage:
            def locator(self, selector):
                self.selector = selector
                return FakeRows()

        page = FakePage()

        row = find_detail_result_avatar(page)

        self.assertEqual(row, "result-row")
        self.assertEqual(page.selector, "tbody.d-table__body tr .head-photo")

    def test_select_search_payload_skips_recommended_results(self):
        payloads = [
            {"success": True, "data": {"kols": [{"redId": "other"}]}},
            {
                "success": True,
                "data": {
                    "kols": [
                        {"redId": "638355164", "name": "Mao嗷嗷呢"},
                    ]
                },
            },
        ]

        payload = select_search_payload(
            payloads,
            Blogger("638355164", "Mao嗷嗷呢"),
        )

        self.assertEqual(payload["data"]["kols"][0]["redId"], "638355164")


if __name__ == "__main__":
    unittest.main()
