import re
import unittest

import requests
from bs4 import BeautifulSoup

from monitor import PAGES, norm, compact


class LivePageDiagnostic(unittest.TestCase):
    def test_live_structure(self):
        for url, names in PAGES.items():
            response = requests.get(url, timeout=25, headers={"Cache-Control":"no-cache"})
            print(f"\n=== SITE {url} ===")
            print(f"status={response.status_code}; encoding={response.encoding}; bytes={len(response.content)}")
            response.raise_for_status()
            soup=BeautifulSoup(response.content, "html.parser")
            for tag in soup(["script", "style", "template"]):
                tag.decompose()
            tokens=[norm(s) for s in soup.stripped_strings]
            print("TOKENS FIRST 40: "+repr(tokens[:40])[:3200])
            for name in names:
                hits=[i for i,t in enumerate(tokens) if compact(name) in compact(t)]
                print("STORE",repr(name),"TOKEN HITS",hits[:20])
                for index in hits[:5]:
                    print("  TOKENS",repr(tokens[max(0,index-6):index+65])[:4500])
                match=re.search(re.escape(name.replace(" ", "")),compact(soup.get_text(" ",strip=True)))
                if match:
                    print("  HTML AROUND STORE:")
                    raw=str(soup)
                    raw_compact=compact(raw)
                    center=raw_compact.find(compact(name))
                    print(raw_compact[max(0,center-250):center+2000][:2250])
            print("UPDATE/LAST MARKERS",repr([t for t in tokens if "更新" in t or "前" in t][:60])[:5000])
            print("HTML top",repr(str(soup)[:800])[:900])
