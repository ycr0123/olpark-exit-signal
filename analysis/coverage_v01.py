"""2025 입출차(659) 원본의 날짜별 결함을 기록 건수만으로 판정해 온전한 날 목록을 쓴다(2026-11-24, 결과와 무관한 자료 품질 규칙).

발견(2026-11-24 verify_h2_v01 실행 뒤): 입차 기준 월별 건수가 8월 65,534, 9월 65,534, 11월 65,477, 12월 65,424 로 다른 달(18만~30만)보다 훨씬 적다.
옛 엑셀 행 한도(65,536)와 거의 같아 제공 쪽 내보내기 잘림으로 보인다(미확인). 꼴은 둘이다:
- 8, 9월: 모든 날에 평소의 약 4분의 1 만 고르게 남음(뽑힌 방식 모름) -> 그 달 전체 제외.
- 11, 12월: 1~6일은 평소 수준이고 7일에서 끊김 -> 그 달에서 기록이 있는 마지막 날(끊긴 날)과 그 뒤 제외.
- 모든 달: 기록 0 인 날(대부분 매달 마지막 날) 제외. 전날이 제외된 날도 제외(밤 출차에 전날 입차 차량이 섞이고 주차 대수 재구성이 끊김).
규칙은 건수만 보고 정했다. 공연 여부나 출차 물결 결과는 보지 않았다.
출력: analysis/coverage_v01.json (valid_days, excluded 와 사유).
"""

import json
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
df = pd.read_parquet(ROOT / "data" / "trips_2025_v01.parquet")
cnt = df.in_t.dt.normalize().value_counts()
mon = df.in_t.dt.to_period("M").value_counts()
CAPPED = [
    str(m)
    for m, n in mon.items()
    if abs(n - 65535) <= 200 and str(m).startswith("2025")
]
excluded = {}
for day in pd.date_range("2025-01-01", "2025-12-31"):
    ds = day.strftime("%Y-%m-%d")
    m = ds[:7]
    n = int(cnt.get(day, 0))
    if n == 0:
        excluded[ds] = "기록 0"
    elif m in CAPPED:
        days_m = sorted(d for d in cnt.index if d.strftime("%Y-%m") == m)
        spread = len(days_m) >= 25
        if spread:
            excluded[ds] = "행 한도 달, 모든 날 일부만 남음"
        elif day >= days_m[-1]:
            excluded[ds] = "행 한도 달, 끊긴 날과 그 뒤"
base = dict(excluded)
for day in pd.date_range("2025-01-01", "2025-12-31"):
    ds = day.strftime("%Y-%m-%d")
    prev = (day - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    if ds not in base and (prev in base or day == pd.Timestamp("2025-01-01")):
        excluded[ds] = "전날 제외"
valid = [
    d.strftime("%Y-%m-%d")
    for d in pd.date_range("2025-01-01", "2025-12-31")
    if d.strftime("%Y-%m-%d") not in excluded
]
out = {
    "capped_months": CAPPED,
    "month_counts_in_t": {str(k): int(v) for k, v in sorted(mon.items())},
    "n_valid": len(valid),
    "valid_days": valid,
    "excluded": dict(sorted(excluded.items())),
}
(ROOT / "analysis" / "coverage_v01.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
)
print("capped", CAPPED, "valid", len(valid), "excluded", len(excluded))
for h, a, b in (("H1", "2025-01-01", "2025-07-01"), ("H2", "2025-07-01", "2026-01-01")):
    print(h, sum(a <= d < b for d in valid))
