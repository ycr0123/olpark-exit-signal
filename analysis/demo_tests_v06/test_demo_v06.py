"""시연 6판 동작 시험. 5판 시험에 5판 좁힌 추가 검증 지적 4건(응답 본문 멈춤, 최근 기록 대기 시간이 판정을 바꿈,
실시간 실패 뒤 최근 기록 곡선, 앞 회차 최근 기록 합치기)을 더했다. 6판 통과, 5판 실패가 기대다.
(5판 설명) 시연 5판 동작 시험. 4판 시험(코덱스 감사 1회차 상급 3, 4, 5)에 2회차 지적을 더했다:
상급 2(공백 문자열, false 를 0대로), 상급 3(최근 기록 요청이 멈추면 실시간 값도 안 나옴, 늦게 온 앞 회차 응답이 최신 값을 덮음),
상급 4(운영자 탭 공연 목록의 날짜 넘김), 중급 6(25~35분 전 비교 기록이 없을 때 다른 시점 차이를 30분 변화로 표시).
같은 시험을 4판에 걸어 결함이 잡히는지도 본다(양방향). 하나라도 실패하면 종료코드 1.
사용: python test_demo_v06.py <demo 폴더>
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


def run(case, t0, recent, live_seq, steps, hook=None):
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
        if hook:
            pg.add_init_script(
                "window.__LIVE=%s;window.__RECENT=%s;"
                % (json.dumps(LIVE), json.dumps(RECENT or ""))
                + hook
            )
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
                schedLinks:document.querySelectorAll('#schedTable a').length,
                schedRows:Math.max(0,document.querySelectorAll('#schedTable tr').length-1),
                opsSvg:document.querySelectorAll('#opsLive svg').length})"""
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

# 2회차 상급 2: 공백 문자열과 false 는 0대가 아니라 받지 못함
for name, bad in (("blank", " "), ("false", False)):
    o = run(
        name,
        kst("2026-11-26T20:00:00"),
        [{"kst": "2026-11-26T19:30:00", "v": 1200}],
        [bad],
        [0],
    )
    res[name + "_rejected"] = (
        "받지 못함" in o[0]["count"]
        and not o[0]["kAmber"]
        and "amber" not in o[0]["lamp"]
    )

# 2회차 상급 3-1: 최근 기록 요청이 끝나지 않아도 실시간 값은 나와야 함
HANG = (
    "(function(){var f=window.fetch;window.fetch=function(u,o){u=String(u);"
    "if(window.__RECENT&&u.indexOf(window.__RECENT)===0)return new Promise(function(){});"
    "return f.apply(this,arguments)}})();"
)
o = run(
    "recent_hang", kst("2026-11-26T20:00:00"), [], [1000], [0, 10 * 1000], hook=HANG
)
res["recent_hang_live_shown"] = o[1]["count"] == "1,000대"

# 2회차 상급 3-2: 첫 회차 실시간 응답이 7분 늦게 오면, 그사이 받은 다음 회차 값을 덮지 않아야 함
LATE = (
    "(function(){var f=window.fetch,n=0;window.fetch=function(u,o){u=String(u);"
    "if(u.indexOf(window.__LIVE)===0){n++;if(n===1)return new Promise(function(res){setTimeout(function(){"
    "res(new Response(JSON.stringify([{parking_sum:1700}]),{status:200,headers:{'content-type':'application/json'}}))"
    "},7*60000)})}return f.apply(this,arguments)}})();"
)
o = run(
    "late_response",
    kst("2026-11-26T20:00:00"),
    [],
    [1100],
    [0, 5 * 60 * 1000, 3 * 60 * 1000],
    hook=LATE,
)
res["late_second_shown"] = o[1]["count"] == "1,100대"
res["late_not_overwritten"] = o[2]["count"] == "1,100대" and "+" not in o[2]["chg"]

# 2회차 상급 4: 자정이 지나면 운영자 탭 공연 목록도 다시 계산
SCHED = json.loads((DEMO / "schedule.json").read_text(encoding="utf-8"))["events"]
exp_before = sum(1 for e in SCHED if e["end"] >= "2026-11-29")
exp_after = sum(1 for e in SCHED if e["end"] >= "2026-11-30")
assert exp_before != exp_after, "시험 날짜를 다시 골라야 함"
o = run(
    "ops_rollover", kst("2026-11-29T23:58:00"), [], [2000, 2000], [0, 5 * 60 * 1000]
)
res["ops_rows_before"] = o[0]["schedRows"] == exp_before
res["ops_rows_after_midnight"] = o[1]["schedRows"] == exp_after

# 2회차 중급 6: 70분 전 기록만 있으면 30분 변화 자리에 70분 차이를 쓰지 않음
o = run(
    "gap70",
    kst("2026-11-26T20:00:00"),
    [{"kst": "2026-11-26T18:50:00", "v": 1500}],
    [1000],
    [0],
)
res["gap70_no_change"] = o[0]["chg"] == "-" and "분 전보다" not in o[0]["label"]

# 5판 좁힌 검증 상급 1: 응답 헤더만 오고 본문이 멈추면 15초 뒤 실패로 표시하고 노란불을 지움
BODYHANG = (
    "(function(){var f=window.fetch,n=0;window.fetch=function(u,o){u=String(u);"
    "if(u.indexOf(window.__LIVE)===0){n++;if(n===2)return Promise.resolve({ok:true,json:function(){return new Promise(function(){})}})}"
    "return f.apply(this,arguments)}})();"
)
o = run(
    "body_hang",
    kst("2026-11-26T20:00:00"),
    [{"kst": "2026-11-26T19:30:00", "v": 1500}],
    [1000, 1000],
    [0, 5 * 60 * 1000, 20 * 1000],
    hook=BODYHANG,
)
res["body_hang_first_yellow"] = o[0]["kAmber"]
res["body_hang_clears"] = (
    "받지 못함" in o[2]["count"] and not o[2]["kAmber"] and "amber" not in o[2]["lamp"]
)

# 5판 좁힌 검증 상급 2: 최근 기록을 기다린 시간이 비교 표본의 나이를 바꾸지 않음(24분 56초 전 기록은 비교 대상이 아님)
AGE = (
    "(function(){try{localStorage.setItem('olpark_samples',JSON.stringify([{t:Date.parse('2026-11-26T19:35:04+09:00'),v:1500}]))}catch(e){}"
    "var f=window.fetch;window.fetch=function(u,o){u=String(u);"
    "if(window.__RECENT&&u.indexOf(window.__RECENT)===0)return new Promise(function(){});"
    "return f.apply(this,arguments)}})();"
)
o = run("wait_age", kst("2026-11-26T20:00:00"), [], [1000], [0, 10 * 1000], hook=AGE)
res["wait_age_no_yellow"] = (
    o[1]["count"] == "1,000대" and not o[1]["kAmber"] and "amber" not in o[1]["lamp"]
)

# 5판 좁힌 검증 상급 3: 실시간이 먼저 실패해도 1초 뒤 받은 최근 기록으로 운영자 곡선을 그림
FAILFIRST = (
    "(function(){var f=window.fetch;window.fetch=function(u,o){u=String(u);var a=arguments,self=this;"
    "if(u.indexOf(window.__LIVE)===0)return Promise.reject(new TypeError('x'));"
    "if(window.__RECENT&&u.indexOf(window.__RECENT)===0)return new Promise(function(res){setTimeout(function(){res(f.apply(self,a))},1000)});"
    "return f.apply(this,arguments)}})();"
)
o = run(
    "fail_then_recent",
    kst("2026-11-26T20:00:00"),
    [
        {"kst": "2026-11-26T19:50:00", "v": 1300},
        {"kst": "2026-11-26T19:55:00", "v": 1250},
    ],
    [1000],
    [0, 3 * 1000],
    hook=FAILFIRST,
)
res["fail_then_recent_curve"] = "받지 못함" in o[1]["count"] and o[1]["opsSvg"] >= 1

# 5판 좁힌 검증 중급 5: 시간 제한을 넘겨 늦게 온 앞 회차 최근 기록은 다음 회차 비교에 섞이지 않음
LATEREC = (
    "(function(){var f=window.fetch,n=0;window.fetch=function(u,o){u=String(u);"
    "if(window.__RECENT&&u.indexOf(window.__RECENT)===0){n++;if(n===1)return new Promise(function(res){setTimeout(function(){"
    "res(new Response(JSON.stringify({samples:[{kst:'2026-11-26T19:35:05',v:1500}]}),{status:200,headers:{'content-type':'application/json'}}))"
    "},5*60000+2000)});return new Promise(function(){})}"
    "return f.apply(this,arguments)}})();"
)
o = run(
    "late_recent",
    kst("2026-11-26T20:00:00"),
    [],
    [1000, 1000],
    [
        0,
        5 * 60 * 1000 + 3 * 1000,
        12 * 1000,
    ],  # 둘째 회차는 최근 기록을 8초까지 기다린 뒤 그린다
    hook=LATEREC,
)
res["late_recent_not_merged"] = not o[2]["kAmber"] and "amber" not in o[2]["lamp"]

print(json.dumps(res, ensure_ascii=False))
ok = all(res.values())
print("ALL_PASS" if ok else "SOME_FAIL")
sys.exit(0 if ok else 1)
