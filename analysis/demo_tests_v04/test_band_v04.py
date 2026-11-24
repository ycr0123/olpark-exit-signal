"""다시 보기 노란 띠의 첫 시각을 화면에서 읽어, 같은 규칙으로 파이썬에서 계산한 값과 대조한다."""

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
DEMO = Path(sys.argv[1])
D = json.loads((DEMO / "data.json").read_text(encoding="utf-8"))
thr = D["live_yellow_drop30"]


def hm(t):
    h, m = map(int, t.split(":"))
    return (h + 24 if h < 6 else h) * 60 + m


exp = {}
for n in D["nights"]:
    xs = [hm(t) for t in n["t"]]
    first = None
    for i in range(len(xs)):
        cand = [
            (abs(xs[i] - xs[k] - 30), k) for k in range(i) if 25 <= xs[i] - xs[k] <= 35
        ]
        if cand and n["v"][min(cand)[1]] - n["v"][i] >= thr:
            first = xs[i]
            break
    exp[n["date"]] = first

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 900})

    def route(r):
        u = r.request.url
        if u.startswith("http://demo.test/"):
            f = DEMO / (u.split("demo.test/")[1].split("?")[0] or "index.html")
            if f.exists():
                return r.fulfill(
                    status=200,
                    body=f.read_bytes(),
                    headers={
                        "content-type": (
                            "text/html" if f.suffix == ".html" else "application/json"
                        )
                        + "; charset=utf-8"
                    },
                )
        return r.fulfill(status=500, body="")

    pg.route("**/*", route)
    pg.goto("http://demo.test/index.html")
    pg.wait_for_timeout(500)
    pg.click("nav button[data-t=replay]")
    got = {}
    for i, n in enumerate(D["nights"]):
        pg.select_option("#nightSel", str(i))
        pg.wait_for_timeout(200)
        got[n["date"]] = pg.evaluate(
            """()=>{const s=document.querySelector('#nightChart svg');const W=+s.getAttribute('viewBox').split(' ')[2];
            const r=[...s.querySelectorAll('rect')];if(!r.length)return null;const x=Math.min(...r.map(e=>+e.getAttribute('x')));
            const L=46,R=10,x0=900,x1=1500;return Math.round(x0+(x-L)/(W-L-R)*(x1-x0));}"""
        )
    b.close()
fmt = lambda m: None if m is None else f"{(m // 60) % 24:02d}:{m % 60:02d}"  # noqa: E731
print({d: (fmt(exp[d]), fmt(got[d])) for d in exp})
print("BAND_PASS" if all(exp[d] == got[d] for d in exp) else "BAND_FAIL")
