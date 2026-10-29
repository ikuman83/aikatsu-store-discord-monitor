import unittest

from monitor import PAGES, ParseError, fetch_page, parse_store_page


class LivePageDiagnostic(unittest.TestCase):
    def test_live_official_store_markup(self):
        parsed = 0
        for url, names in PAGES.items():
            html, checked_at = fetch_page(url)
            for name in names:
                try:
                    machines = parse_store_page(html, url, (name,), checked_at)
                except ParseError as exc:
                    # Stores can disappear from search results temporarily.
                    print(f"UNAVAILABLE: {name}: {exc}", flush=True)
                    continue
                self.assertGreater(len(machines), 0)
                self.assertEqual(len({m.number for m in machines}), len(machines))
                parsed += len(machines)
                for machine in machines:
                    self.assertEqual(machine.store, name)
                    self.assertGreater(machine.number, 0)
                    print(f"{name} / {machine.number}台目 / {machine.label}", flush=True)
        self.assertGreater(parsed, 0)


if __name__ == "__main__":
    unittest.main()
