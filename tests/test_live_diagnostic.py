import unittest

from monitor import PAGES, fetch_page, parse_store_page


class LivePageDiagnostic(unittest.TestCase):
    def test_live_official_store_markup(self):
        for url, names in PAGES.items():
            html, checked_at = fetch_page(url)
            machines = parse_store_page(html, url, names, checked_at)
            self.assertEqual({machine.store for machine in machines}, set(names))
            for store in names:
                items = [machine for machine in machines if machine.store == store]
                self.assertGreater(len(items), 0)
                self.assertEqual(len({m.number for m in items}), len(items))
                for machine in items:
                    self.assertIsNotNone(machine.updated_at)
                    self.assertGreater(machine.number, 0)
                    print(f"{store} / {machine.number}台目 / {machine.label} / "
                          f"{machine.updated_at.isoformat()} / "
                          f"{machine.age_minutes:.1f}分前", flush=True)


if __name__ == "__main__":
    unittest.main()
