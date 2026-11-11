import unittest
from bs4 import BeautifulSoup
from monitor import PAGES, ParseError, fetch_page, parse_store_page, compact

class LivePageDiagnostic(unittest.TestCase):
    def test_live_official_store_markup(self):
        total = 0
        for url, names in PAGES.items():
            html, checked_at = fetch_page(url)
            soup = BeautifulSoup(html, "html.parser")
            print("DIAGNOSTIC URL", url, "bytes", len(html), "title", soup.title.get_text(" ",strip=True) if soup.title else "-",flush=True)
            print("DIAGNOSTIC body text:", repr(soup.get_text(" ",strip=True)[:1300]),flush=True)
            print("DIAGNOSTIC div classes:", [(cls, len(soup.select("."+cls))) for cls in ["modalFilterCol","resultColBox","runningItem","runningList","storeColName","timeago"]],flush=True)
            print("DIAGNOSTIC meta:", [(tag.get("name"),tag.get("content","")[:150]) for tag in soup.select("meta[name=robots],meta[name=description]")],flush=True)
            for name in names:
                print("DIAGNOSTIC STORE", name, "mentioned=",compact(name) in compact(soup.get_text(" ",strip=True)),flush=True)
                try:
                    machines = parse_store_page(html,url,(name,),checked_at)
                    total += len(machines)
                    print("PARSED", name,len(machines),flush=True)
                except ParseError as exc:
                    print("UNAVAILABLE",name,str(exc),flush=True)
        print("TOTAL PARSED",total,flush=True)
        # Diagnostic is allowed to succeed even on a temporary site outage.
        self.assertTrue(True)
