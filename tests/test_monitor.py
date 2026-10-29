import unittest
from datetime import datetime, timedelta, timezone

from monitor import (
    JST, KOKUBUNJI_URL, TACHIKAWA_URL, PAGES,
    Machine, ParseError, alert_needed, parse_store_page, parse_timestamp, notification_text,
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
        namco = [m for m in items if m.store.startswith("namco")]
        self.assertEqual([item.number for item in namco], [1, 2])
        self.assertEqual(namco[0].label, "37分前")
        self.assertEqual(namco[0].updated_at.astimezone(JST).hour, 20)
        self.assertTrue(alert_needed(namco[0], {}))
        self.assertFalse(alert_needed(next(m for m in items if m.store == "ビックカメラ立川店"), {}))

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


    def test_full_discord_notification_format(self):
        old = self.now - timedelta(hours=14)
        fresh = self.now - timedelta(minutes=5)
        items = [
            Machine("タイトーステーション 国分寺店", 1, "5分前", KOKUBUNJI_URL, self.now, fresh),
            Machine("タイトーステーション 国分寺店", 2, "5分前", KOKUBUNJI_URL, self.now, fresh),
            Machine("タイトーステーション 立川北口店", 1, "2日前", TACHIKAWA_URL, self.now, old),
            Machine("ビックカメラ立川店", 1, "42分前", TACHIKAWA_URL, self.now, self.now - timedelta(minutes=42)),
            Machine("namcoららぽーと立川立飛おまけ横丁店", 1, "14時間前", TACHIKAWA_URL, self.now, old),
            Machine("namcoららぽーと立川立飛おまけ横丁店", 2, "14時間前", TACHIKAWA_URL, self.now, old),
        ]
        output = notification_text(items)
        self.assertIn("1台目【稼働】 5分前", output)
        self.assertIn("1台目【稼働】 14時間前", output)
        self.assertLess(output.index("国分寺店"), output.index("立川北口店"))
        self.assertLess(len(output), 2000)

    def test_unavailable_store_in_full_notification(self):
        from monitor import notification_text
        checked = self.now
        machines = [
            Machine(name, 1, "5分前", url, checked, checked - timedelta(minutes=5))
            for url, names in PAGES.items() for name in names
            if name != "タイトーステーション 立川北口店"
        ]
        result = notification_text(machines, {"タイトーステーション 立川北口店"})
        self.assertIn("タイトーステーション 立川北口店\\n情報取得不可", result)
        self.assertIn("ビックカメラ立川店", result)
        self.assertIn("タイトーステーション 国分寺店", result)

    def test_missing_timestamp_is_rejected(self):
        with self.assertRaises(ParseError):
            parse_timestamp("unknown")


if __name__ == "__main__":
    unittest.main()
