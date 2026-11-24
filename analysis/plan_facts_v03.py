"""기획서 4판에 들어가는 수치를 원천에서 직접 계산해 analysis/plan_facts_v03.json 에 쓴다(2026-11-24). 판정이 아니라 기술 통계와 시험 결과 모음.

3판(plan_facts_v02) 대비, 코덱스 감사 1회차 상급 1 반영:
- 'span'(첫 포화 칸부터 마지막 포화 칸 끝까지 간격)은 그 시점의 포화 상태가 아니다. 이름을 last_within60(마지막 포화 칸이 첫 포화 뒤 60분 안에 끝난 밤)으로 바꿔 함께 둔다.
- 시점별 포화 상태를 새로 센다: 첫 포화 칸 + k분(k = 0, 10, ..., 120) 칸이 포화인 밤 수와, 그 칸이 관측창(23:50) 안에 있는 밤 수(분모).
- 22시 이후 첫 포화 밤을 뺀 민감도, 첫 포화 시각 25~75분위 안에 든 밤 수, 출구 추천 시험의 적중 칸 수(분모 포함)를 둔다.
- '노란불부터 1시간' 같은 권고 기준은 여기서 만들지 않는다(시험하지 않은 기준).

원천: data/trips_2025_v01.parquet(659 2,411,225건 중 형식 해석 2,411,022건), analysis/coverage_v01.json(온전한 날),
analysis/kcisa675_events_v01.csv(675 공연), 시험 결과 json(exit_after_show_v03, verify_h2_v02, verify_gate_v01),
실시간 기록 live_log/samples.csv(환경변수 OLPARK_LIVE_LOG 로 바꿀 수 있음).
포화 정의는 verify_h2_v02 와 같다(주출구 동2, 북2, 남2 의 10분 출차가 상반기 온전한 날 99.9분위의 90% 이상, 18:00~23:50).
'노란불' = 실시간 주차 대수가 10분 사이 theta 대 이상 줄어든 상태(theta = verify_h2_v02 의 상반기 공연 없는 날 밤 99분위). 포화 감지기가 아니라 측정값 표시다.
"""

import csv
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
A = ROOT / "analysis"
cov = json.loads((A / "coverage_v01.json").read_text(encoding="utf-8"))
VALID = set(cov["valid_days"])
T_EXIT = json.loads((A / "exit_after_show_v03.json").read_text(encoding="utf-8"))
T_H2 = json.loads((A / "verify_h2_v02.json").read_text(encoding="utf-8"))
T_GATE = json.loads((A / "verify_gate_v01.json").read_text(encoding="utf-8"))
df = pd.read_parquet(ROOT / "data" / "trips_2025_v01.parquet")
ev = defaultdict(lambda: {"aud": 0, "names": set()})
rows675 = 0
with open(A / "kcisa675_events_v01.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        rows675 += 1
        ev[r["date"]]["aud"] = max(ev[r["date"]]["aud"], int(r["audience"]))
        ev[r["date"]]["names"].add(r["name"])
MAIN = ["동2", "북2", "남2"]
cap = T_H2["cap_h1_p999"]
theta = T_H2["theta_h1_non_event_p99_drop10"]

gate10 = (
    df.assign(ob=df.out_t.dt.floor("10min"))
    .groupby(["ob", "out_gate"])
    .size()
    .unstack(fill_value=0)
)
util = pd.DataFrame({g: gate10[g] / cap[g] for g in MAIN})
dayk = util.index.strftime("%Y-%m-%d")
nightmask = util.index.hour >= 18
idx = pd.date_range("2024-12-01", "2026-01-01", freq="10min")
dd = df[df.in_t >= "2024-12-01"]
occ = (
    dd.in_t.dt.floor("10min").value_counts().reindex(idx, fill_value=0)
    - dd.out_t.dt.floor("10min").value_counts().reindex(idx, fill_value=0)
).cumsum()
drop = occ.shift(1) - occ


def half(ds):
    return "H1" if ds < "2025-07-01" else "H2"


per_day = {}
for ds in sorted(VALID):
    m = nightmask & (dayk == ds)
    u = util[m]
    sat = u[(u >= 0.9).any(axis=1)]
    day = pd.Timestamp(ds)
    w = pd.date_range(
        day + pd.Timedelta(hours=18),
        day + pd.Timedelta(hours=23, minutes=50),
        freq="10min",
    )
    ex = gate10.reindex(w, fill_value=0)[MAIN].sum(axis=1)
    satflag = (util.reindex(w).fillna(0)[MAIN] >= 0.9).any(
        axis=1
    )  # 출차 기록 없는 칸 = 0 = 포화 아님
    after = {}
    if len(sat):
        t0 = sat.index.min()
        for k in range(0, 130, 10):
            tk = t0 + pd.Timedelta(minutes=k)
            after[k] = None if tk > w[-1] else bool(satflag.loc[tk])
    per_day[ds] = {
        "after": after,
        "event": ds in ev,
        "half": half(ds),
        "sat_min": int(len(sat) * 10),
        "first_sat": sat.index.min().strftime("%H:%M") if len(sat) else None,
        "span_min": int((sat.index.max() - sat.index.min()).total_seconds() / 60 + 10)
        if len(sat)
        else 0,
        "peak30_main": int(ex.rolling(3).sum().max()),
        "yellow": bool((drop.reindex(w) >= theta).any()),
    }


def rate(h, evf):
    ds = [
        d
        for d, v in per_day.items()
        if v["event"] == evf and (h == "ALL" or v["half"] == h)
    ]
    k = sum(per_day[d]["sat_min"] > 0 for d in ds)
    return {"days": len(ds), "sat_days": int(k), "rate": k / len(ds) if ds else None}


sat_rates = {
    h: {"event": rate(h, True), "non_event": rate(h, False)}
    for h in ("H1", "H2", "ALL")
}
dur = [v["sat_min"] for v in per_day.values() if v["event"] and v["sat_min"] > 0]
dur_q = {str(q): float(np.quantile(dur, q)) for q in (0.25, 0.5, 0.75, 0.9)}
share_over30 = float(np.mean(np.array(dur) > 30))
span = [v["span_min"] for v in per_day.values() if v["event"] and v["sat_min"] > 0]
span_q = {str(q): float(np.quantile(span, q)) for q in (0.25, 0.5, 0.75, 0.9)}
span_le40 = float(np.mean(np.array(span) <= 40))
span_le60 = float(np.mean(np.array(span) <= 60))
first_sat = [v["first_sat"] for v in per_day.values() if v["event"] and v["first_sat"]]
fs_min = [int(t[:2]) * 60 + int(t[3:]) for t in first_sat]
first_q = {str(q): float(np.quantile(fs_min, q)) for q in (0.1, 0.25, 0.5, 0.75, 0.9)}

# 포화 칸에서 다른 주출구 여유
sat_bins = util[
    nightmask
    & dayk.isin([d for d, v in per_day.items() if v["event"]])
    & (util >= 0.9).any(axis=1)
]
other_min = []
for t, row in sat_bins.iterrows():
    s = [g for g in MAIN if row[g] >= 0.9]
    o = [g for g in MAIN if g not in s]
    if o:
        other_min.append(min(row[g] for g in o))
gate_sat = {
    h: {
        g: int(
            (
                (util[g] >= 0.9)
                & nightmask
                & dayk.isin(
                    [d for d, v in per_day.items() if v["event"] and v["half"] == h]
                )
            ).sum()
        )
        for g in MAIN
    }
    for h in ("H1", "H2")
}
yellow_ev = [v["yellow"] for v in per_day.values() if v["event"]]
yellow_non = [v["yellow"] for v in per_day.values() if not v["event"]]

# 실시간 기록
live = pd.read_csv(Path(os.environ.get("OLPARK_LIVE_LOG", ROOT / "live_log" / "samples.csv")))
live = live[live.status == "ok"].copy()
live["kst"] = pd.to_datetime(live.kst)
live = live.set_index("kst").parking_sum
nights = {}
for day in sorted(set(live.index.normalize())):
    s = live[day + pd.Timedelta(hours=18) : day + pd.Timedelta(hours=23, minutes=59)]
    if len(s) < 60:
        continue
    r30 = s - s.shift(-6)
    t = r30.idxmax()
    nights[day.strftime("%Y-%m-%d")] = {
        "max_drop30": int(r30.max()),
        "from": t.strftime("%H:%M"),
        "level_from": int(s[t]),
        "samples": int(len(s)),
    }

mon = cov["month_counts_in_t"]
full_months = [
    v for k, v in mon.items() if k.startswith("2025") and k not in cov["capped_months"]
]


# ---- 2026-11-24 비판 점검 뒤 추가한 기술 통계(판정 아님, 통과선 없음) ----
def _rate(days):
    k = sum(per_day[d]["sat_min"] > 0 for d in days)
    return {
        "days": len(days),
        "sat_days": int(k),
        "rate": k / len(days) if days else None,
    }


_wk = {d: pd.Timestamp(d).dayofweek >= 5 for d in per_day}  # 토, 일
_aud_med = float(np.median([ev[d]["aud"] for d in per_day if per_day[d]["event"]]))
_e675 = pd.read_csv(A / "kcisa675_events_v01.csv", encoding="utf-8-sig")
_g675 = _e675.groupby("name")["audience"].agg(["count", "nunique"])
_m675 = _g675[_g675["count"] >= 2]
extras = {
    "audience_same_all_days": {
        "multi_day_shows": int(len(_m675)),
        "same_value": int((_m675["nunique"] == 1).sum()),
    },
    "weekday_split": {
        "event_weekend": _rate([d for d in per_day if per_day[d]["event"] and _wk[d]]),
        "event_weekday": _rate(
            [d for d in per_day if per_day[d]["event"] and not _wk[d]]
        ),
        "non_event_weekend": _rate(
            [d for d in per_day if not per_day[d]["event"] and _wk[d]]
        ),
        "non_event_weekday": _rate(
            [d for d in per_day if not per_day[d]["event"] and not _wk[d]]
        ),
    },
    "audience_split_valid_event_median": _aud_med,
    "audience_split": {
        "ge_median": _rate(
            [d for d in per_day if per_day[d]["event"] and ev[d]["aud"] >= _aud_med]
        ),
        "lt_median": _rate(
            [d for d in per_day if per_day[d]["event"] and ev[d]["aud"] < _aud_med]
        ),
    },
    "h2_valid_by_month": {
        m: {
            "valid": sum(1 for d in per_day if d.startswith(m)),
            "event": sum(1 for d in per_day if d.startswith(m) and per_day[d]["event"]),
        }
        for m in sorted({d[:7] for d in per_day if per_day[d]["half"] == "H2"})
    },
    "span_first_sat_ge_2200": int(sum(t >= "22:00" for t in first_sat)),
    "span_first_sat_eq_1800": int(sum(t == "18:00" for t in first_sat)),
    "span_by_half_le60": {
        h: float(
            np.mean(
                [
                    v["span_min"] <= 60
                    for v in per_day.values()
                    if v["event"] and v["sat_min"] > 0 and v["half"] == h
                ]
            )
        )
        for h in ("H1", "H2")
    },
}

# ---- 2026-11-24 코덱스 감사 1회차 반영(판정 아님, 통과선 없음) ----
_evsat = {d: v for d, v in per_day.items() if v["event"] and v["sat_min"] > 0}
after_k = {}
for k in range(0, 130, 10):
    obs = [v["after"][k] for v in _evsat.values() if v["after"][k] is not None]
    after_k[str(k)] = {"observable": len(obs), "saturated": int(sum(obs))}
_early = {d: v for d, v in _evsat.items() if v["first_sat"] < "22:00"}
_lo, _hi = first_q["0.25"], first_q["0.75"]
_h2non = [v for v in per_day.values() if not v["event"] and v["half"] == "H2"]
extras["v03"] = {
    "event_sat_nights": len(_evsat),
    "saturated_at_first_plus": after_k,
    "last_within60_after_first": {
        "nights": int(sum(v["span_min"] <= 60 for v in _evsat.values())),
        "of": len(_evsat),
    },
    "last_within60_first_before_2200": {
        "nights": int(sum(v["span_min"] <= 60 for v in _early.values())),
        "of": len(_early),
    },
    "first_sat_in_q25_q75": {
        "nights": int(sum(_lo <= m <= _hi for m in fs_min)),
        "of": len(fs_min),
    },
    "gate_rule_counts": {
        "n": T_GATE["h2_n"],
        "hit": int(sum(v["hit"] for v in T_GATE["by_gate"].values())),
        "alt_lower": int(
            round(T_GATE["alt_lower_than_saturated_rate"] * T_GATE["h2_n"])
        ),
        "random_expected": round(
            T_GATE["random_other_below_0_6_expected"] * T_GATE["h2_n"], 1
        ),
    },
    "realtime_T2_counts": {
        "sat_bins": T_H2["T2"]["h2_event_sat_bins"],
        "caught": T_H2["T2"]["caught"],
        "non_event_nights": T_H2["T2"]["h2_non_event_days"],
        "fired_nights": T_H2["T2"]["false_nights"],
        "non_event_nights_without_sat": int(sum(v["sat_min"] == 0 for v in _h2non)),
        "fired_on_nights_without_sat": int(
            sum(v["sat_min"] == 0 and v["yellow"] for v in _h2non)
        ),
        "fired_nights_recount": int(sum(v["yellow"] for v in _h2non)),
    },
}
assert (
    extras["v03"]["realtime_T2_counts"]["fired_nights_recount"]
    == T_H2["T2"]["false_nights"]
), "per_day yellow 정의가 verify_h2_v02 T2 와 다름"

out = {
    "extras": extras,
    "records_total": int(T_EXIT["unique_rows"]),
    "records_parsed": int(len(df)),
    "valid_days": len(VALID),
    "valid_days_by_half": {
        h: sum(1 for d in VALID if half(d) == h) for h in ("H1", "H2")
    },
    "capped_months": cov["capped_months"],
    "month_counts_in_t": mon,
    "full_month_median": float(np.median(full_months)),
    "rows675": rows675,
    "event_days_2025": len(ev),
    "audience_max_2025": int(max(v["aud"] for v in ev.values())),
    "audience_median_2025": float(np.median([v["aud"] for v in ev.values()])),
    "event_days_valid": sum(1 for d in VALID if d in ev),
    "cap": cap,
    "sat_rates": sat_rates,
    "sat_minutes_event_nights_q": dur_q,
    "sat_over30_share": share_over30,
    "sat_span_first_to_last_q": span_q,
    "sat_span_le40_share": span_le40,
    "sat_span_le60_share": span_le60,
    "first_sat_minute_of_day_q": first_q,
    "event_first_sat_list": sorted(first_sat),
    "event_span_list": sorted(span),
    "other_gate_min_util_q": {
        str(q): float(np.quantile(other_min, q)) for q in (0.25, 0.5, 0.75)
    },
    "other_gate_below_0_6_share": float(np.mean(np.array(other_min) < 0.6)),
    "sat_bins_by_gate": gate_sat,
    "peak30_main_event_median": float(
        np.median([v["peak30_main"] for v in per_day.values() if v["event"]])
    ),
    "peak30_main_non_event_median": float(
        np.median([v["peak30_main"] for v in per_day.values() if not v["event"]])
    ),
    "theta_drop10": theta,
    "yellow_nights_event": {"n": len(yellow_ev), "fired": int(sum(yellow_ev))},
    "yellow_nights_non_event": {"n": len(yellow_non), "fired": int(sum(yellow_non))},
    "tests": {
        "exit_time_mae": T_EXIT["time_mae_min"],
        "exit_size_mae": T_EXIT["size_mae"],
        "exit_test_n": T_EXIT["test_n"],
        "exit_train_median_delay_min": T_EXIT["train_median_delay_min"],
        "arrival_T1": {
            k: T_H2["T1"][k]
            for k in ("mae_A_line", "mae_B_const", "pass", "h2_event_days")
        },
        "realtime_T2": {
            k: T_H2["T2"][k]
            for k in ("recall", "false_rate", "h2_non_event_days", "pass")
        },
        "gate_rule": {
            k: T_GATE[k]
            for k in (
                "hit_rate_alt_below_0_6",
                "alt_lower_than_saturated_rate",
                "random_other_below_0_6_expected",
                "h2_n",
                "pass",
            )
        },
    },
    "live": {
        "first": str(live.index.min()),
        "last": str(live.index.max()),
        "n": int(len(live)),
        "nights": nights,
    },
}
(A / "plan_facts_v03.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
)
print(
    json.dumps(
        {
            k: out[k]
            for k in (
                "sat_rates",
                "sat_minutes_event_nights_q",
                "sat_over30_share",
                "first_sat_minute_of_day_q",
                "other_gate_below_0_6_share",
                "sat_bins_by_gate",
                "peak30_main_event_median",
                "peak30_main_non_event_median",
                "yellow_nights_event",
                "yellow_nights_non_event",
                "event_days_2025",
                "event_days_valid",
                "rows675",
                "full_month_median",
            )
        },
        ensure_ascii=False,
        indent=1,
    )
)
print(json.dumps(out["live"], ensure_ascii=False))
