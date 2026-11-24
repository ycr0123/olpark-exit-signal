"""2025 입출차(659) 원본 쪽 파일을 한 표(차량 1대 = 1행)로 묶어 data/trips_2025_v01.parquet 로 저장한다(2026-11-24).

열: lid, in_gate, in_lane, in_t, out_gate, out_lane, out_t. 문 이름은 '동2문입구#1' 에서 '동2', 차로 '1'. 'CMB'(통합 부스로 보임, 미확인)는 차로 'CMB'.
점검(실패하면 멈춤): 고유 LOCAL_ID 수 == totalCount, 입차, 출차 시각 해석 실패 수를 출력.
"""

import gzip
import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
RAWS = [ROOT / "data" / "raw" / "kcisa659", ROOT / "data" / "raw" / "kcisa659_n5000"]
OUT = ROOT / "data" / "trips_2025_v01.parquet"
pat = re.compile(
    r"입구:(?P<ig>[^,#]*?)문(?:입구#(?P<il>\d+)|(?P<ic>CMB)), 입차시간:(?P<it>[\d\- :]{19}), "
    r"출구:(?P<og>[^,#]*?)문(?:출구#(?P<ol>\d+)|(?P<oc>CMB)), 출차시간:(?P<ot>[\d\- :]{19})"
)
rows, seen, total, bad = [], set(), None, 0
for raw in RAWS:
    for f in sorted(raw.glob("p*.json.gz")):
        d = json.loads(gzip.decompress(f.read_bytes()).decode("utf-8"))
        body = d.get("response", d)["body"]
        total = int(body["totalCount"])
        it = body["items"]
        if isinstance(it, dict):
            it = it.get("item", [])
        for r in it:
            lid = r["LOCAL_ID"]
            if lid in seen:
                continue
            seen.add(lid)
            m = pat.search(r.get("DESCRIPTION") or "")
            if not m:
                bad += 1
                continue
            rows.append(
                (lid, m["ig"], m["il"] or "CMB", m["it"], m["og"], m["ol"] or "CMB", m["ot"])
            )
print("unique", len(seen), "total", total, "unparsed", bad)
if len(seen) != total:
    raise SystemExit("STOP unique != totalCount")
df = pd.DataFrame(
    rows, columns=["lid", "in_gate", "in_lane", "in_t", "out_gate", "out_lane", "out_t"]
)
df["in_t"] = pd.to_datetime(df["in_t"], errors="coerce")
df["out_t"] = pd.to_datetime(df["out_t"], errors="coerce")
print("bad times", int(df["in_t"].isna().sum()), int(df["out_t"].isna().sum()))
print(df["in_gate"].value_counts().to_dict())
print(df["out_gate"].value_counts().to_dict())
print("out range", df["out_t"].min(), df["out_t"].max())
df.to_parquet(OUT, index=False)
print("rows", len(df), "->", OUT)
