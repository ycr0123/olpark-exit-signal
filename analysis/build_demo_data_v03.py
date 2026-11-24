"""시연 3판 데이터(demo-v03/data.json, demo-v03/schedule.json)를 만든다(2026-11-24, 비판 점검 반영).

2판 대비: 기술 통계(평일끼리 비교, 관람객 규모별, 하반기 구성, 지속 시간 잘림)를 넣고, 최근 기록 파일 주소(RECENT_URL)를 둔다.
RECENT_URL 은 공개 저장소의 자동 작업이 남기는 최근 3시간 기록이다. 시험해 작동을 확인하기 전에는 None 으로 둔다.

입력: analysis/plan_facts_v02.json, 실시간 기록 samples.csv(5분 주차 대수, 공개 값만), demo/schedule_v02.json(기관 누리집 공연 일정).
공연 날 밤 다시 보기는 실시간 기록이 있는 밤(15:00~다음날 01:00)만 넣는다. 공연 여부와 시작 시각은 공식 일정과 공연 상세 페이지에서 확인한 값만 쓴다.
"""

import json
import os
import shutil
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "demo-v03"
OUT.mkdir(exist_ok=True)
F = json.loads((ROOT / "analysis" / "plan_facts_v02.json").read_text(encoding="utf-8"))
SHOW_START = {  # 공식 공연 상세(evtSeq=5158) 확인값. 새 밤을 넣을 때는 확인 뒤 추가.
    "2026-11-21": {
        "title": "2026-27 로이킴 LIVE TOUR [R:O:Y] in SEOUL",
        "venue": "KSPO DOME",
        "start": "18:00",
    },
    "2026-11-22": {
        "title": "2026-27 로이킴 LIVE TOUR [R:O:Y] in SEOUL",
        "venue": "KSPO DOME",
        "start": "17:00",
    },
}
LIVE_YELLOW = 400
RECENT_URL = "https://raw.githubusercontent.com/ycr0123/olpark-exit-signal/live/recent.json"  # 2026-11-24 11:48 KST actions run ok, CORS *

live = pd.read_csv(Path(os.environ.get("OLPARK_LIVE_LOG", ROOT / "live_log" / "samples.csv")))
live = live[live.status == "ok"].copy()
live["kst"] = pd.to_datetime(live.kst)
live = live.set_index("kst").parking_sum
nights = []
for day in sorted(set(live.index.normalize())):
    s = live[day + pd.Timedelta(hours=15) : day + pd.Timedelta(hours=25)]
    if len(s) < 100:
        continue
    ds = day.strftime("%Y-%m-%d")
    nights.append(
        {
            "date": ds,
            "weekday": "월화수목금토일"[day.dayofweek],
            "show": SHOW_START.get(ds),
            "t": [t.strftime("%H:%M") for t in s.index],
            "v": [int(x) for x in s.values],
            "max_drop30": F["live"]["nights"].get(ds, {}).get("max_drop30"),
        }
    )

R = F["sat_rates"]
data = {
    "generated": "2026-11-24",
    "live_api": "https://www.ksponco.or.kr/online/main/parkingorsApi.do?apiKey=PARKING21803504",
    "live_yellow_drop30": LIVE_YELLOW,
    "recent_url": RECENT_URL,
    "extras": F["extras"],
    "audience_median": F["audience_median_2025"],
    "h2_valid_days": F["valid_days_by_half"]["H2"],
    "records_total": F["records_total"],
    "valid_days": F["valid_days"],
    "sat_rates": {
        h: {k: {"days": v["days"], "sat_days": v["sat_days"]} for k, v in R[h].items()}
        for h in R
    },
    "span_list": F["event_span_list"],
    "span_le40": F["sat_span_le40_share"],
    "span_le60": F["sat_span_le60_share"],
    "span_median": F["sat_span_first_to_last_q"]["0.5"],
    "first_sat_list": F["event_first_sat_list"],
    "gate_sat": F["sat_bins_by_gate"],
    "cap": F["cap"],
    "peak30_event": F["peak30_main_event_median"],
    "peak30_non": F["peak30_main_non_event_median"],
    "event_days_2025": F["event_days_2025"],
    "month_counts": {
        k: v for k, v in F["month_counts_in_t"].items() if k.startswith("2025")
    },
    "capped_months": F["capped_months"],
    "tests": F["tests"],
    "nights": nights,
}
(OUT / "data.json").write_text(
    json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
)
sch = json.loads((ROOT / "demo" / "schedule_v02.json").read_text(encoding="utf-8"))
(OUT / "schedule.json").write_text(
    json.dumps(sch, ensure_ascii=False, indent=1), encoding="utf-8"
)
shutil.copy2(ROOT / "analysis" / "plan_facts_v02.json", OUT / "facts.json")
print(
    "nights",
    [(n["date"], len(n["v"])) for n in nights],
    "bytes",
    (OUT / "data.json").stat().st_size,
)
