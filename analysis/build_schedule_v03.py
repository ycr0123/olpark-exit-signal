"""기관 누리집 공연 일정 목록(저장본)에서 공연 기간과 공연 상세 주소를 읽어 demo-v04/schedule.json 을 만든다(2026-11-24).

3판(demo/schedule_v02.json, 손으로 옮긴 목록) 대비: 공연마다 공식 공연 상세 주소(evtSeq)를 붙인다(코덱스 감사 1회차 상급 5).
입력: reference/20261124/eventlist_1250.html (https://www.ksponco.or.kr/olympicpark/eventInfo/eventInfoListText?mid=a20301010200, 2026-11-24 12:5x 1회 받음)
검사: 읽은 공연 수가 상세 링크 수와 같아야 한다. --check-against <옛 목록 json> 을 주면 옛 목록의 모든 공연(제목, 기간, 공연장)을 포함해야 한다. 다르면 멈춘다.
사용: python build_schedule_v03.py [저장본 html] [출력 경로] [--check-against 옛 목록]
  (이 작업 폴더에서는 인자 없이 실행하면 아래 기본 경로와 3판 목록 대조를 쓴다)
"""

import html
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
_args = [a for a in sys.argv[1:] if not a.startswith("--")]
_chk = sys.argv[sys.argv.index("--check-against") + 1] if "--check-against" in sys.argv else None
if _chk:
    _args.remove(_chk)
DEFAULT = not sys.argv[1:]
SRC = Path(_args[0]) if _args else ROOT / "reference" / "20261124" / "eventlist_1250.html"
OLD = Path(_chk) if _chk else (ROOT / "demo" / "schedule_v02.json" if DEFAULT else None)
LIST_URL = (
    "https://www.ksponco.or.kr/olympicpark/eventInfo/eventInfoListText?mid=a20301010200"
)
BASE = "https://www.ksponco.or.kr"
OUT = Path(_args[1]) if len(_args) > 1 else ROOT / "demo-v04" / "schedule.json"

t = SRC.read_text(encoding="utf-8")
pat = re.compile(
    r'<a href="(/olympicpark/eventInfo/eventInfoView\.es\?mid=a20301010200&amp;evtSeq=(\d+))" class="title">(.*?)</a></td>\s*'
    r'<td><span class="date">(\d{4}-\d{2}-\d{2}) ~ (\d{4}-\d{2}-\d{2})</span></td>\s*'
    r'<td><em class="place">(.*?)</em></td>',
    re.S,
)
events = []
for m in pat.finditer(t):
    events.append(
        {
            "title": html.unescape(m.group(3)).strip(),
            "start": m.group(4),
            "end": m.group(5),
            "venue": html.unescape(m.group(6)).strip(),
            "url": BASE + html.unescape(m.group(1)),
        }
    )
n_links = len(re.findall(r"eventInfoView\.es\?mid=a20301010200&amp;evtSeq=\d+\"", t))
if len(events) != n_links or not events:
    sys.exit(f"BLOCK parsed {len(events)} != title links {n_links}")

old = json.loads(OLD.read_text(encoding="utf-8")) if OLD else {"events": []}
key = lambda e: (e["title"], e["start"], e["end"], e["venue"])  # noqa: E731
new_keys = {key(e) for e in events}
missing = [key(e) for e in old["events"] if key(e) not in new_keys]
if missing:
    sys.exit(f"BLOCK 3판 목록에 있는데 저장본에 없음: {missing}")

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(
    json.dumps(
        {"source": LIST_URL, "fetched_kst": "2026-11-24 12:5x", "events": events},
        ensure_ascii=False,
        indent=1,
    ),
    encoding="utf-8",
)
print("events", len(events), "old", len(old["events"]), "->", OUT)
