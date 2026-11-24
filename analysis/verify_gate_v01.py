"""출구 추천 규칙 시험(2026-11-24 11시대 작성, 실행 전 커밋). 온전한 날(coverage_v01.json)만 쓴다.

배경: verify_h2_v02 에서 공연일 밤 출구 포화(주출구 10분 출차가 상반기 99.9분위 cap 의 90% 이상)가 하반기에도 반복됐고(23/26),
포화 칸의 48% 에서 다른 주출구 이용률이 0.6 미만이었다. 이번 시험은 '어느 출구로 돌아가라'를 상반기에서 정해 하반기에 맞는지 본다.
이 스크립트 전에는 출구별 조건부 이용률을 하반기에서 보지 않았다(상반기도 보지 않았다. 규칙은 아래처럼 상반기에서 자동으로 정한다).

정의(앞 판과 같음): 주출구 동2, 북2, 남2. cap = 상반기 온전한 날 출구별 10분 출차 99.9분위. 포화 칸 = 18:00~23:50 10분 칸에서 출구 이용률(출차/cap) >= 0.9.
규칙 만들기(상반기 공연일만): 출구 g 가 포화된 칸마다 다른 두 주출구의 이용률을 보고, 이용률 중앙값이 더 낮은 쪽을 g 의 '돌아갈 출구' alt[g] 로 정한다.
시험(하반기 공연일): 출구 g 포화 칸에서 alt[g] 이용률 < 0.6 이면 '추천이 맞음'.
통과 = 하반기 공연일 포화 칸 전체(출구별 칸을 모두 셈)에서 추천이 맞은 비율 >= 0.60, 그리고 alt[g] 가 g 보다 이용률이 낮았던 비율 >= 0.80.
비교 기준(기술만): 다른 두 주출구 중 무작위 하나를 골랐을 때 이용률 < 0.6 비율의 기댓값.
기획서 반영 규칙(결과 전 고정): 통과면 '공연 날 밤 X문이 막히면 Y문으로' 안내를 기획서 핵심 기능으로 쓴다. 실패면 출구별 포화 빈도 지도만 쓰고 돌아갈 출구 추천은 쓰지 않는다.
기술(통과선 없음): 출구별 포화 칸 수와 공연 시작 시간대(675 first_hour)별 포화 시각 분포(공연 시간대 끝 기준 분).
출력: analysis/verify_gate_v01.json
"""

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
VALID = set(
    json.loads((ROOT / "analysis" / "coverage_v01.json").read_text(encoding="utf-8"))[
        "valid_days"
    ]
)
df = pd.read_parquet(ROOT / "data" / "trips_2025_v01.parquet")
ev = defaultdict(lambda: {"last": -1, "first": 99})
with open(ROOT / "analysis" / "kcisa675_events_v01.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        e = ev[r["date"]]
        e["last"] = max(e["last"], int(r["last_hour"]))
        e["first"] = min(e["first"], int(r["first_hour"]))
MAIN = ["동2", "북2", "남2"]
gate10 = (
    df.assign(ob=df.out_t.dt.floor("10min"))
    .groupby(["ob", "out_gate"])
    .size()
    .unstack(fill_value=0)
)
for g in MAIN:
    if g not in gate10:
        gate10[g] = 0
day_of = gate10.index.strftime("%Y-%m-%d")
in_h1 = (
    (gate10.index >= "2025-01-01") & (gate10.index < "2025-07-01") & day_of.isin(VALID)
)
cap = {g: float(gate10.loc[in_h1, g].quantile(0.999)) for g in MAIN}
util = pd.DataFrame({g: gate10[g] / cap[g] for g in MAIN})
night = (util.index.hour >= 18) & day_of.isin(VALID) & day_of.isin(list(ev.keys()))
U1 = util[night & (util.index < "2025-07-01")]
U2 = util[night & (util.index >= "2025-07-01") & (util.index < "2026-01-01")]

alt = {}
for g in MAIN:
    s = U1[U1[g] >= 0.9]
    others = [o for o in MAIN if o != g]
    alt[g] = min(others, key=lambda o: float(s[o].median())) if len(s) else None

hit = lower = n = 0
rand_hit = 0.0
by_gate = defaultdict(lambda: {"n": 0, "hit": 0})
for g in MAIN:
    s = U2[U2[g] >= 0.9]
    others = [o for o in MAIN if o != g]
    for _, row in s.iterrows():
        n += 1
        ok = row[alt[g]] < 0.6
        hit += int(ok)
        lower += int(row[alt[g]] < row[g])
        rand_hit += np.mean([row[o] < 0.6 for o in others])
        by_gate[g]["n"] += 1
        by_gate[g]["hit"] += int(ok)
hit_rate = hit / n if n else None
lower_rate = lower / n if n else None
passed = bool(n and hit_rate >= 0.60 and lower_rate >= 0.80)

timing = defaultdict(list)
for t, row in util[night & ((util >= 0.9).any(axis=1))].iterrows():
    ds = t.strftime("%Y-%m-%d")
    end = pd.Timestamp(ds) + pd.Timedelta(hours=ev[ds]["last"] + 1)
    timing[ev[ds]["first"]].append((t - end).total_seconds() / 60)

out = {
    "cap": cap,
    "alt_rule_from_h1": alt,
    "h1_sat_bins_by_gate": {g: int((U1[g] >= 0.9).sum()) for g in MAIN},
    "h2_sat_bins_by_gate": {g: int((U2[g] >= 0.9).sum()) for g in MAIN},
    "h2_n": n,
    "hit_rate_alt_below_0_6": hit_rate,
    "alt_lower_than_saturated_rate": lower_rate,
    "random_other_below_0_6_expected": rand_hit / n if n else None,
    "by_gate": dict(by_gate),
    "pass": passed,
    "describe_sat_minutes_from_block_end_by_first_hour": {
        str(k): {
            "n": len(v),
            "median": float(np.median(v)),
            "q25": float(np.quantile(v, 0.25)),
            "q75": float(np.quantile(v, 0.75)),
        }
        for k, v in sorted(timing.items())
    },
}
(ROOT / "analysis" / "verify_gate_v01.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
)
print(json.dumps(out, ensure_ascii=False, indent=1))
