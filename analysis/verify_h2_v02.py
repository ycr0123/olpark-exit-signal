"""2025 하반기(7~12월) 시험: 기획서 2판의 세 주장을 결과 보기 전에 고정한 기준으로 잰다(2026-11-24 11시대 작성, 실행 전 커밋).

배경: 상반기 탐색(explore_h1_v01.py, explore_h1_v02.py, 판정 아님)에서 공연일 밤 출구 포화(출구 10분 처리량이 상반기 99.9분위의 90% 이상)가
공연일 53/73일, 공연 없는 날 13/108일에 나왔다. 하반기는 이 스크립트 전에는 열지 않았다(exit_after_show_v02 는 연간 최고 물결 시각과 크기만 봄).

공통 정의(상반기에서만 정함):
- 주출구 = 동2, 북2, 남2. 처리량 상한 cap[g] = 상반기 출구 g 의 10분 출차 수 99.9분위.
- 포화 칸 = 18:00~23:50 의 10분 칸 중 주출구 하나라도 cap 의 90% 이상.
- 공연일 = kcisa675_events_v01.csv 에 공연이 있는 날. 공연 없는 날 = 그 밖의 날.
- 주차 대수(실시간 API 대리값) = 입차 누적 - 출차 누적(10분, 상대값). 실시간 API 는 세 주차장 합계 한 숫자라서 출구 구분 없이 전체로 만든다.

T1 도착 쪽 예보(공연일): 하루 순증가 = 그날 06:00~23:50 주차 대수 최댓값 - 06:00 값.
  A = 상반기 공연일로 맞춘 직선(순증가 ~ 관람객 수). B = 상반기 공연일 순증가 중앙값.
  통과 = 하반기 공연일 평균 절대 오차가 A 가 B 보다 20% 이상 작다.
T2 실시간 신호가 포화를 잡는가:
  신호 = 18:00 이후 10분 칸의 주차 대수 감소량(직전 칸 - 이번 칸) >= theta.
  theta = 상반기 공연 없는 날 밤(18:00~23:50) 10분 감소량의 99분위(상반기에서만 정함).
  포착 = 포화 칸 t 에 대해 신호가 t-20분 ~ t 사이 칸 중 하나에서 울림.
  통과 = 하반기 공연일 포화 칸 포착률 >= 0.70 이고, 하반기 공연 없는 날 중 밤에 신호가 한 번이라도 울린 날 비율 <= 0.20.
T3 출구 여유(기술만, 통과선 없음): 하반기 공연일 포화 칸에서 가장 한산한 주출구 이용률(10분 출차 / cap) 분포와 0.6 미만 비율.
기술(통과선 없음): 하반기 포화 발생 일수(공연일, 공연 없는 날), 공연일 하루 포화 총 분, 출구별 포화 칸 수.

기획서 반영 규칙(결과 전 고정): T1 실패면 도착 예보를 쓰지 않는다. T2 실패면 '실시간 신호로 포화를 알린다'를 쓰지 않고 1년 기록의 출구 지도만 쓴다.
출력: analysis/verify_h2_v01.json (스크립트가 직접 씀).
v02(2026-11-24 11시대, 실행 전 커밋): 기준, 정의, 통과선은 앞 판과 같다. 바꾼 것은 하나뿐이다:
analysis/coverage_v01.json 의 온전한 날(valid_days)만 쓴다. 원본에 8, 9월 일부만 남음, 11, 12월 7일 끊김, 매달 마지막 날 0건 결함이 있어
앞 판의 시험 구간 절반 이상이 결함이었다(coverage_v01.py 에 규칙과 근거). 규칙은 건수만 보고 정했다.
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
df = pd.read_parquet(ROOT / "data" / "trips_2025_v01.parquet")
ev = defaultdict(lambda: {"aud": 0})
with open(ROOT / "analysis" / "kcisa675_events_v01.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        ev[r["date"]]["aud"] = max(ev[r["date"]]["aud"], int(r["audience"]))
MAIN = ["동2", "북2", "남2"]
H1 = (pd.Timestamp("2025-01-01"), pd.Timestamp("2025-07-01"))
H2 = (pd.Timestamp("2025-07-01"), pd.Timestamp("2026-01-01"))

ob = df.out_t.dt.floor("10min")
gate10 = df.assign(ob=ob).groupby(["ob", "out_gate"]).size().unstack(fill_value=0)
VALID = set(json.loads((Path(__file__).resolve().parent / "coverage_v01.json").read_text(encoding="utf-8"))["valid_days"])
g1 = gate10[(gate10.index >= H1[0]) & (gate10.index < H1[1])]
g1 = g1[g1.index.strftime("%Y-%m-%d").isin(VALID)]
cap = {g: float(g1[g].quantile(0.999)) for g in MAIN}

idx = pd.date_range("2024-12-01", "2026-01-01", freq="10min")
dd = df[df.in_t >= "2024-12-01"]
ins = dd.in_t.dt.floor("10min").value_counts().reindex(idx, fill_value=0)
outs = dd.out_t.dt.floor("10min").value_counts().reindex(idx, fill_value=0)
occ = (ins - outs).cumsum()
drop = occ.shift(1) - occ


def night(day):
    return pd.date_range(
        day + pd.Timedelta(hours=18),
        day + pd.Timedelta(hours=23, minutes=50),
        freq="10min",
    )


def days(rng):
    return [
        d
        for d in pd.date_range(rng[0], rng[1] - pd.Timedelta(days=1))
        if d.strftime("%Y-%m-%d") in VALID
    ]


# theta 는 상반기 공연 없는 날 밤에서만
h1_non = [
    d
    for d in days(H1)
    if d.strftime("%Y-%m-%d") not in ev and d > pd.Timestamp("2025-01-01")
]
theta = float(
    np.percentile(
        np.concatenate([drop.reindex(night(d)).to_numpy() for d in h1_non]), 99
    )
)


def rise(day):
    o = occ[day + pd.Timedelta(hours=6) : day + pd.Timedelta(hours=23, minutes=50)]
    return float(o.max() - o.iloc[0])


h1_ev = [
    d
    for d in days(H1)
    if d.strftime("%Y-%m-%d") in ev and d > pd.Timestamp("2025-01-01")
]
h2_ev = [d for d in days(H2) if d.strftime("%Y-%m-%d") in ev]
h2_non = [d for d in days(H2) if d.strftime("%Y-%m-%d") not in ev]
xs = np.array([ev[d.strftime("%Y-%m-%d")]["aud"] for d in h1_ev], float)
ys = np.array([rise(d) for d in h1_ev])
slope, icpt = np.polyfit(xs, ys, 1)
b_const = float(np.median(ys))
xt = np.array([ev[d.strftime("%Y-%m-%d")]["aud"] for d in h2_ev], float)
yt = np.array([rise(d) for d in h2_ev])
mae_a = float(np.mean(np.abs(slope * xt + icpt - yt)))
mae_b = float(np.mean(np.abs(b_const - yt)))
t1_pass = mae_a <= 0.8 * mae_b


def sat_bins(day):
    w = night(day)
    u = gate10.reindex(w, fill_value=0)
    for g in MAIN:
        if g not in u:
            u[g] = 0
    util = pd.DataFrame({g: u[g] / cap[g] for g in MAIN})
    return util[(util >= 0.9).any(axis=1)], util


caught = total = 0
slack = []
sat_min = []
gate_cnt = defaultdict(int)
for d in h2_ev:
    s, util = sat_bins(d)
    sat_min.append(len(s) * 10)
    for t in s.index:
        total += 1
        win = drop.reindex(pd.date_range(t - pd.Timedelta(minutes=20), t, freq="10min"))
        caught += int((win >= theta).any())
        slack.append(float(s.loc[t].min()))
        for g in MAIN:
            if s.loc[t, g] >= 0.9:
                gate_cnt[g] += 1
recall = caught / total if total else None
false_nights = sum(int((drop.reindex(night(d)) >= theta).any()) for d in h2_non)
false_rate = false_nights / len(h2_non)
t2_pass = recall is not None and recall >= 0.70 and false_rate <= 0.20
non_sat_days = sum(int(len(sat_bins(d)[0]) > 0) for d in h2_non)
ev_sat_days = sum(int(m > 0) for m in sat_min)

out = {
    "cap_h1_p999": cap,
    "theta_h1_non_event_p99_drop10": theta,
    "T1": {
        "h1_event_days": len(h1_ev),
        "h2_event_days": len(h2_ev),
        "slope_per_audience": float(slope),
        "intercept": float(icpt),
        "const_median": b_const,
        "mae_A_line": mae_a,
        "mae_B_const": mae_b,
        "pass": bool(t1_pass),
    },
    "T2": {
        "h2_event_sat_bins": total,
        "caught": caught,
        "recall": recall,
        "h2_non_event_days": len(h2_non),
        "false_nights": false_nights,
        "false_rate": false_rate,
        "pass": bool(t2_pass),
    },
    "T3": {
        "n": len(slack),
        "min_util_quantiles": {
            str(q): float(np.quantile(slack, q)) for q in (0.1, 0.25, 0.5, 0.75, 0.9)
        }
        if slack
        else None,
        "share_min_util_below_0_6": float(np.mean(np.array(slack) < 0.6))
        if slack
        else None,
    },
    "describe": {
        "h2_event_days_with_sat": ev_sat_days,
        "h2_event_days": len(h2_ev),
        "h2_non_event_days_with_sat": non_sat_days,
        "h2_non_event_days": len(h2_non),
        "event_sat_minutes_quantiles": {
            str(q): float(np.quantile(sat_min, q)) for q in (0.25, 0.5, 0.75, 0.9)
        },
        "sat_bins_by_gate": dict(gate_cnt),
    },
}
(ROOT / "analysis" / "verify_h2_v02.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
)
print(json.dumps(out, ensure_ascii=False, indent=1))
