"""기관 실시간 주차현황을 한 번 받아 최근 4시간 기록(recent.json)에 덧붙인다.

공개 저장소의 자동 작업(.github/workflows/record-live.yml)이 5분마다 부른다.
인자: 이전 기록 파일, 새 기록 파일 [--init]. 받기에 실패하면 이전 기록을 그대로 쓰고 실패를 status 에 남긴다(값을 지어내지 않음).
이전 기록을 읽지 못하면 멈춘다(종료코드 3). 빈 기록에서 시작하는 것은 live 브랜치가 아직 없을 때 --init 을 준 경우뿐이다.
그래서 이전 기록 가져오기가 실패한 회차가 다음 성공 회차에 기록을 표본 하나로 덮어쓰지 않는다.
"""

import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://www.ksponco.or.kr/online/main/parkingorsApi.do?apiKey=PARKING21803504"
KST = timezone(timedelta(hours=9))
KEEP = timedelta(hours=4)

prev_path, out_path = sys.argv[1], sys.argv[2]
INIT = "--init" in sys.argv[3:]
if INIT:
    prev = {"samples": []}
else:
    try:
        with open(prev_path, encoding="utf-8") as f:
            prev = json.load(f)
        assert isinstance(prev.get("samples"), list)
    except (OSError, ValueError, AssertionError, AttributeError) as e:
        print(f"BLOCK prev unreadable: {type(e).__name__}")
        sys.exit(3)
now = datetime.now(KST)
samples = [
    s
    for s in prev.get("samples", [])
    if now - datetime.fromisoformat(s["kst"]).replace(tzinfo=KST) <= KEEP
]
status = "ok"
try:
    req = urllib.request.Request(
        API, headers={"User-Agent": "olpark-exit-signal/1.0 (public data contest demo)"}
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        v = int(json.loads(r.read().decode("utf-8"))[0]["parking_sum"])
    samples.append({"kst": now.strftime("%Y-%m-%dT%H:%M:%S"), "v": v})
except Exception as e:  # noqa: BLE001
    status = f"fetch_failed: {type(e).__name__}"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(
        {
            "updated_kst": now.strftime("%Y-%m-%dT%H:%M:%S"),
            "status": status,
            "samples": samples,
        },
        f,
        ensure_ascii=False,
    )
print(status, len(samples))
