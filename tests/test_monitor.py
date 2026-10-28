import unittest
from datetime import datetime, timedelta, timezone

from monitor import (
    JST, KOKUBUNJI_URL, TACHIKAWA_URL, PAGES,
    Machine, ParseError, alert_needed, parse_store_page, parse_timestamp,
)

HTML = """
<html><body>
<div class="resultColBox">namcoららぽーと立川立飛おまけ横丁店</div>
<div class="modalFilterCol"><div class="storeInfoRow">
<h3 class="storeColName">namcoららぽーと立川立飛おまけ横丁店</h3></div>
<ul class="runningList">
<li class="runningItem"><div class="runningItemNum"><span class="num">1</span><span>台目</span></div>
<div class="runningItemTime">最終更新:<span class="timeago" title="2026-10-2820:23:02">37分前</span></div></li>
<li class="runningItem"><div class="runningItemNum"><span class="num">2</span></div>
<div class="runningItemTime">最終更新:<span class="timeago" title="2026-10-2820:23:05">37分前</span></div></li>
</ul></div>
<div class="modalFilterCol"><div class="storeInfoRow"><h3 class="storeColName">
タイトーステーション 立川北口店</h3></div><ul class="runningList">
<li class="runningItem"><div class="runningItemNum"><span class="num">1</span></div>
<div class="runningItemTime"><span class="timeago" title="2026-10-2620:00:00">2日前</span></div></li>
</ul></div>
<div class="modalFilterCol"><div class="storeInfoRow"><h3 class="storeColName">
ビックカメラ立川店</h3></div><ul class="runningList">
<li class="runningItem"><div class="runningItemNum"><span class="num">1</span></div>
<div class="runningItemTime"><span class="timeago" title="2026-10-2810:00:00">11時間前</span></div></li>
</ul></div>
</body></html>
"""


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)

    def test_machine_parser_with_official_markup(self):
        items = parse_store_page(
            HTML, TACHIKAWA_URL, PAGES[TACHIKAWA_URL], self.now
        )
        self.assertEqual(len(items), 4)
        self.assertEqual([item.number for item in items[:2]], [1, 2])
        self.assertEqual(items[0].label, "37分前")
        self.assertEqual(items[0].updated_at.astimezone(JST).hour, 20)
        self.assertTrue(alert_needed(items[0], {}))
        self.assertFalse(alert_needed(items[-1], {}))

    def test_exact_timestamp_and_boundary(self):
        self.assertEqual(
            parse_timestamp("2026-10-28 20:23:02"),
            parse_timestamp("2026-10-2820:23:02")
        )
        machine = Machine("A", 1, "1時間前", TACHIKAWA_URL, self.now,
                          self.now - timedelta(minutes=60))
        self.assertTrue(alert_needed(machine, {}))
        older = Machine("A", 1, "1時間前", TACHIKAWA_URL, self.now,
                        self.now - timedelta(minutes=60, seconds=1))
        self.assertFalse(alert_needed(older, {}))
        future = Machine("A", 1, "今", TACHIKAWA_URL, self.now,
                         self.now + timedelta(seconds=30))
        self.assertFalse(alert_needed(future, {}))

    def test_no_duplicate_notification(self):
        first = Machine("A", 1, "1分前", TACHIKAWA_URL, self.now,
                        self.now - timedelta(minutes=1))
        self.assertTrue(alert_needed(first, {}))
        sent = {first.key: first.updated_at.isoformat()}
        same = Machine("A", 1, "21分前", TACHIKAWA_URL,
                       self.now + timedelta(minutes=20), first.updated_at)
        self.assertFalse(alert_needed(same, sent))
        newer = Machine("A", 1, "2分前", TACHIKAWA_URL,
                        self.now + timedelta(minutes=20),
                        self.now + timedelta(minutes=18))
        self.assertTrue(alert_needed(newer, sent))

    def test_missing_store_is_rejected(self):
        with self.assertRaises(ParseError):
            parse_store_page(HTML, KOKUBUNJI_URL, PAGES[KOKUBUNJI_URL], self.now)

    def test_missing_timestamp_is_rejected(self):
        with self.assertRaises(ParseError):
            parse_timestamp("unknown")


if __name__ == "__main__":
    unittest.main()
