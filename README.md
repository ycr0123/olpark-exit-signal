# 올팍 출구 신호등

공연 날 밤, 지금 나가도 될지 판단할 재료를 보여 주는 올림픽공원 주차 출구 안내입니다. 2026년도 한국체육산업개발 공공데이터 활용 경진대회 응모작입니다.

- 시연: https://ycr0123.github.io/olpark-exit-signal/
- 화면은 기관 실시간 주차현황 API(공공데이터포털 15168686)를 브라우저에서 5분마다 직접 부릅니다. 서버와 개인정보 저장이 없습니다.
- `.github/workflows/record-live.yml` 이 5분마다 같은 API를 한 번 불러 `live` 브랜치의 `recent.json`(최근 4시간)을 갱신합니다. 처음 연 사람도 30분 변화를 바로 보게 하려는 장치입니다. GitHub 예약 실행은 늦거나 건너뛸 수 있고, 그때 화면은 브라우저가 연 뒤 받은 값으로 계산합니다.
- 기록 작업은 `live` 브랜치가 있는데 이전 기록을 읽지 못하면 실패로 멈추고 덮어쓰지 않습니다. 빈 기록에서 시작하는 것은 `live` 브랜치가 없을 때뿐입니다.

## 파일

| 경로 | 내용 |
|---|---|
| index.html | 시연 화면(지금, 공연 날 밤 다시 보기, 2025년 기록, 운영자) |
| data.json, facts.json | 2025 입출차 재집계와 시험 결과(analysis/build_demo_data_v04.py 가 생성) |
| schedule.json | 기관 누리집 공연 일정 목록에서 읽은 공연 기간과 공연 상세 주소(analysis/build_schedule_v03.py 가 생성) |
| tools/record_recent.py | 실시간 값을 받아 최근 4시간 기록을 갱신 |
| analysis/ | 수집, 결함 점검, 재집계, 사전 등록 시험, 수치 산출, 화면 동작 시험 스크립트와 그 결과 |

## 다시 만들기(저장소 루트에서)

1) `python analysis/kcisa_collect_v02.py 659 10000 400 60 659` 와 `python analysis/kcisa_collect_v02.py 675 10000 50 60 675`: 문화공공데이터광장에서 2025 입출차(15159093)와 연계 데이터(15164822)를 `data/raw/kcisa659`, `data/raw/kcisa675` 에 받습니다. 키는 직접 발급받아 `private/kcisa-keys.txt` 에 `659=키`, `675=키` 꼴로 두어야 합니다.
   - 실제 수집 때는 서버가 228쪽에서 계속 시간 초과(504)를 내서, 남은 범위를 5천 행 단위로 `kcisa_collect_range_v01.py` 로 받아 `data/raw/kcisa659_n5000` 에 두었습니다. 분석 스크립트는 두 폴더를 함께 읽고, 두 번째 폴더가 없으면 첫 폴더만 읽습니다. 어느 쪽이든 고유 LOCAL_ID 수가 API 의 totalCount 와 같지 않으면 멈춥니다.
2) `python analysis/build_trips_cache_v01.py`, `python analysis/coverage_v01.py`: 차량 한 대를 한 행으로 묶고, 날짜별 건수로 잘린 날(65,535건 안팎에서 끊긴 달, 매달 마지막 날 0건)을 찾습니다.
3) `python analysis/kcisa675_events_v01.py`: 연계 데이터에서 공연 기록이 있는 날과 관람객 기재값을 뽑습니다.
4) `exit_after_show_v03.py`, `verify_h2_v02.py`, `verify_gate_v01.py`: 상반기에서 정한 규칙을 하반기 결함 없는 날로 시험합니다. 통과선은 각 스크립트 맨 위에 있습니다.
5) `python analysis/plan_facts_v03.py`: 기획서와 화면의 모든 수치를 `analysis/plan_facts_v03.json` 으로 냅니다. 실시간 기록 CSV 경로는 환경변수 `OLPARK_LIVE_LOG` 로 줍니다.
6) 공연 일정: 기관 공연 일정 목록(https://www.ksponco.or.kr/olympicpark/eventInfo/eventInfoListText?mid=a20301010200)을 내려받아 `python analysis/build_schedule_v03.py <저장한 html> schedule.json`.
7) `python analysis/build_demo_data_v04.py .`: 루트의 `data.json`, `facts.json` 을 만듭니다(`schedule.json` 이 먼저 있어야 함).
8) 화면 동작 시험: `python analysis/demo_tests_v04/test_demo_v04.py .`(30분 기준, 실패 뒤 표시 초기화, 빈 값 거부, 날짜 넘김, 공연 상세 링크), `python analysis/demo_tests_v04/test_band_v04.py .`(다시 보기 노란 띠 시각). Playwright 가 필요합니다.

원자료(약 241만 건)는 용량 때문에 올리지 않았습니다. 위 1)로 다시 받을 수 있습니다.
