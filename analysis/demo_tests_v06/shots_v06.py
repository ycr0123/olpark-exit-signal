"""시연 5판 화면 캡처와 치수 점검(폭 1280, 390 x 밝은, 어두운 테마 x 탭 4개). 실시간 API 는 정상 값 하나로 흉내 낸다.
판정: 본문 가로 넘침 0, 표 넘침 0, JS 오류 0. 캡처는 <출력 폴더> 에 남긴다(사람 눈 확인용).
사용: python shots_v06.py <demo 폴더> <출력 폴더>
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
DEMO, OUT = Path(sys.argv[1]), Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
D = json.loads((DEMO / "data.json").read_text(encoding="utf-8"))
LIVE = D["live_api"].split("?")[0]
KST = timezone(timedelta(hours=9))
T0 = datetime(2026, 11, 27, 21, 30, tzinfo=KST)
recent = [
    {
        "kst": (T0 - timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:%S"),
        "v": 2100 - (35 - m) * 15,
    }
    for m in range(35, 0, -5)
]
bad = []
with sync_playwright() as p:
    b = p.chromium.launch()
    for scheme in ("light", "dark"):
        for w in (1280, 390):
            pg = b.new_page(viewport={"width": w, "height": 900}, color_scheme=scheme)
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))

            def route(r):
                u = r.request.url
                if u.startswith(LIVE):
                    return r.fulfill(
                        status=200,
                        body=json.dumps([{"parking_sum": 1500}]),
                        headers={
                            "access-control-allow-origin": "*",
                            "content-type": "application/json",
                        },
                    )
                if D["recent_url"] and u.startswith(D["recent_url"]):
                    return r.fulfill(
                        status=200,
                        body=json.dumps({"samples": recent}),
                        headers={
                            "access-control-allow-origin": "*",
                            "content-type": "application/json",
                        },
                    )
                if u.startswith("http://demo.test/"):
                    f = DEMO / (u.split("demo.test/")[1].split("?")[0] or "index.html")
                    if f.exists():
                        return r.fulfill(
                            status=200,
                            body=f.read_bytes(),
                            headers={
                                "content-type": (
                                    "text/html"
                                    if f.suffix == ".html"
                                    else "application/json"
                                )
                                + "; charset=utf-8"
                            },
                        )
                return r.fulfill(status=404, body="")

            pg.route("**/*", route)
            pg.clock.install(time=T0)
            pg.goto("http://demo.test/index.html")
            pg.wait_for_timeout(700)
            for tab in ("now", "replay", "year", "ops"):
                pg.click(f"nav button[data-t={tab}]")
                pg.wait_for_timeout(300)
                m = pg.evaluate(
                    """()=>({page:document.documentElement.scrollWidth-document.documentElement.clientWidth,
                    tables:[...document.querySelectorAll('section.on table')].map(t=>t.scrollWidth-t.parentElement.clientWidth).filter(x=>x>1).length})"""
                )
                if m["page"] > 0 or m["tables"]:
                    bad.append((scheme, w, tab, m))
                pg.screenshot(path=str(OUT / f"{scheme}-{w}-{tab}.png"), full_page=True)
            if errs:
                bad.append((scheme, w, "errors", errs))
            pg.close()
    b.close()
print("issues", bad)
print("SHOTS_PASS" if not bad else "SHOTS_FAIL")
sys.exit(0 if not bad else 1)
