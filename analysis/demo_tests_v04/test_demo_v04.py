"""시연 4판 동작 시험(코덱스 감사 1회차 상급 3, 4, 5 재현 상황). 같은 시험을 3판에 걸어 결함이 잡히는지도 본다(양방향).
사용: python test_demo_v04.py <demo 폴더>
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
DEMO = Path(sys.argv[1])
KST = timezone(timedelta(hours=9))
ORIGIN = "http://demo.test/"
data = json.loads((DEMO / "data.json").read_text(encoding="utf-8"))
LIVE = data["live_api"].split("?")[0]
RECENT = data["recent_url"]


def run(case, t0, recent, live_seq, steps):
    """live_seq: 호출마다 돌려줄 값(None=실패, 'null'=parking_sum null, 정수)."""
    calls = {"n": 0}
    out = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1280, "height": 900})

        def route(r):
            u = r.request.url
            if u.startswith(LIVE):
                i = min(calls["n"], len(live_seq) - 1)
                calls["n"] += 1
                v = live_seq[i]
                if v is None:
                    return r.fulfill(status=500, body="err")
                body = json.dumps([{"parking_sum": None if v == "null" else v}])
                return r.fulfill(
                    status=200,
                    body=body,
                    headers={
                        "content-type": "application/json",
                        "access-control-allow-origin": "*",
                    },
                )
            if RECENT and u.startswith(RECENT):
                return r.fulfill(
                    status=200,
                    body=json.dumps({"samples": recent}),
                    headers={
                        "content-type": "application/json",
                        "access-control-allow-origin": "*",
                    },
                )
            if u.startswith(ORIGIN):
                name = u[len(ORIGIN) :].split("?")[0] or "index.html"
                f = DEMO / name
                if f.exists():
                    ct = "text/html" if name.endswith(".html") else "application/json"
                    return r.fulfill(
                        status=200,
                        body=f.read_bytes(),
                        headers={"content-type": ct + "; charset=utf-8"},
                    )
            return r.fulfill(status=404, body="")

        pg.route("**/*", route)
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.clock.install(time=t0)
        pg.goto(ORIGIN + "index.html")
        pg.wait_for_timeout(500)
        for k, act in enumerate(steps):
            if act:
                pg.clock.fast_forward(act)
                pg.wait_for_timeout(500)
            out[k] = pg.evaluate(
                """()=>({count:document.getElementById('nowCount').textContent,chg:document.getElementById('chg').textContent,
                label:document.getElementById('chgLabel').textContent,kAmber:document.getElementById('kChange').classList.contains('amber'),
                lamp:document.getElementById('lamp').className,advice:document.getElementById('advice').textContent,
                show:document.getElementById('showToday').textContent,showLinks:document.querySelectorAll('#showSub a').length,
                schedLinks:document.querySelectorAll('#schedTable a').length})"""
            )
        out["errors"] = errs
        b.close()
    print(case, json.dumps(out, ensure_ascii=False))
    return out


def kst(s):
    return datetime.fromisoformat(s).replace(tzinfo=KST)


res = {}
# 상급 3: 19:25 1450, 19:30 1350, 20:00 1000 -> 정확한 30분 감소 350, 노란불 아님
o = run(
    "base30",
    kst("2026-11-26T20:00:00"),
    [
        {"kst": "2026-11-26T19:26:00", "v": 1450},
        {"kst": "2026-11-26T19:30:00", "v": 1350},
    ],
    [1000],
    [0],
)
res["base30"] = (
    o[0]["chg"] == "-350대" and not o[0]["kAmber"] and "amber" not in o[0]["lamp"]
)
# 상급 4: 노란불 뒤 실패 -> 변화 카드와 노란 표시가 지워져야
o = run(
    "fail_after_yellow",
    kst("2026-11-26T20:00:00"),
    [{"kst": "2026-11-26T19:30:00", "v": 1450}],
    [1000, None],
    [0, 5 * 60 * 1000],
)
res["yellow_first"] = o[0]["kAmber"] and "노란불" in o[0]["label"]
res["fail_clears"] = (
    (not o[1]["kAmber"])
    and "amber" not in o[1]["lamp"]
    and o[1]["chg"] == "-"
    and "받지 못함" in o[1]["count"]
)
# 상급 4: parking_sum null -> 0대로 처리하지 않음
o = run(
    "null",
    kst("2026-11-26T20:00:00"),
    [{"kst": "2026-11-26T19:30:00", "v": 1000}],
    ["null"],
    [0],
)
res["null_rejected"] = (
    "받지 못함" in o[0]["count"]
    and not o[0]["kAmber"]
    and "한꺼번에" not in o[0]["advice"]
)
# 상급 5: 자정 넘김과 공연 상세 링크
o = run("rollover", kst("2026-11-26T23:58:00"), [], [2000, 2000], [0, 5 * 60 * 1000])
res["before_midnight_none"] = o[0]["show"] == "없음"
res["after_midnight_shows"] = o[1]["show"] == "2건" and o[1]["showLinks"] == 2
res["sched_links"] = o[0]["schedLinks"] >= 3
print(json.dumps(res, ensure_ascii=False))
print("ALL_PASS" if all(res.values()) else "SOME_FAIL")
