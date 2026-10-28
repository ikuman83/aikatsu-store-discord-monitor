import unittest
from datetime import datetime, timedelta, timezone

from monitor import (
    TACHIKAWA_URL, KOKUBUNJI_URL, PAGES, Machine, ParseError,
    age_in_minutes, alert_needed, parse_store_page,
)

HTML = """
<html><body>
<div id="search">
<span>namcoららぽーと立川立飛おまけ横丁店</span>
<span>タイトーステーション 立川北口店</span>
<span>ビックカメラ立川店</span>
</div>
<div class="detail"><h3>namcoららぽーと立川立飛おまけ横丁店</h3>
<b>1台目</b><span>最終更新：</span><span>49分前</span>
<b>2台目</b><span>最終更新：49分前</span></div>
<div class="detail"><h3>タイトーステーション 立川北口店</h3>
<b>1台目</b><span>最終更新：2日前</span>
<b>2台目</b><span>最終更新：2日前</span></div>
<div class="detail"><h3>ビックカメラ立川店</h3>
<b>1台目</b><span>最終更新：11時間前</span></div>
</body></html>"""


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)

    def test_machine_parser(self):
        items = parse_store_page(
            HTML, TACHIKAWA_URL, PAGES[TACHIKAWA_URL], self.now
        )
        self.assertEqual(len(items), 5)
        self.assertEqual([item.label for item in items[:2]], ["49分前", "49分前"])

    def test_fresh_time_interpretation(self):
        self.assertEqual(age_in_minutes("59分前"), 59)
        self.assertEqual(age_in_minutes("数分前"), 3)
        self.assertIsNone(age_in_minutes("1時間前"))
        self.assertEqual(age_in_minutes("0分前"), 0)
        self.assertEqual(age_in_minutes("60分前"), 60)

    def test_no_duplicate_notification(self):
        first = Machine("A", 1, "1分前", TACHIKAWA_URL, self.now)
        self.assertTrue(alert_needed(first, {}))
        sent = {first.key: first.update_estimate.isoformat()}
        same = Machine(
            "A", 1, "21分前", TACHIKAWA_URL, self.now + timedelta(minutes=20)
        )
        self.assertFalse(alert_needed(same, sent))
        newer = Machine(
            "A", 1, "2分前", TACHIKAWA_URL, self.now + timedelta(minutes=20)
        )
        self.assertTrue(alert_needed(newer, sent))

    def test_missing_shop_is_rejected(self):
        with self.assertRaises(ParseError):
            parse_store_page(HTML, KOKUBUNJI_URL, PAGES[KOKUBUNJI_URL], self.now)


if __name__ == "__main__":
    unittest.main()
