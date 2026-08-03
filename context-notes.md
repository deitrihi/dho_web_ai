# 2단계 컨텍스트 노트

## 스키마 전략 결정
- 사용자 확정: 카테고리별 전용 테이블 (EAV 방식 아님). 이유: 로컬 LLM이 Text-to-SQL로
  질의할 때 컬럼명이 명확해야 정확도가 높아짐.
- 참고 ERD 없음. 원본 사이트 구조를 그대로 반영 ([[schema-design-no-erd-reference]]).

## 구현 방식
70개 카테고리마다 처음부터 BeautifulSoup 파싱을 새로 짜지 않기 위해 2단계로 나눔.
1. 범용 추출기: 상세 페이지 HTML은 전부 `div.flex.gap-4 > div(label) + div(value)` 행 반복
   구조를 씀 (표 형태 값은 `<table>` 포함). 이 패턴이 70개 카테고리 샘플 전수 확인 결과
   예외 없이 일관됨 (`all_categories_fields.txt` 참고).
2. 카테고리별 매핑: 범용 추출 결과(스테이징)를 전용 테이블 컬럼으로 pivot하는 선언적 매핑.

## 관찰된 공통 표 패턴 (재사용 가능한 관계 테이블 후보)
- `필요=TABLE(종류,내용)`: equipment, job, major, quest, research, transmutation,
  treasureHuntTheme, treasureMap, legacy 등 다수
- `보상=TABLE(종류,내용)`: quest, research, legacy 등
- `획득 방법=TABLE(레시피 책,레시피,스킬,재료)`: cannon, furniture, tradeGoods, shipMaterial 등
- `획득 방법=TABLE(아이템)`: crest, figurehead(변성연금 별도), ornament, sailorEquipment,
  ship, studdingSail 등
- `획득 방법=TABLE(판매 NPC,지역,장소)`: extraArmor, recipeBook, shipDecor 등
- `변성연금=TABLE(정책,스킬,재료)`: cannon, equipment, extraArmor, figurehead, studdingSail 등
  (transmutation 카테고리 자체와 연결되는 부분 — transmutation 테이블 확인 후 재검토 필요)

이 패턴들은 "완전히 동일한 의미"라고 확정하기 전에 실제 값 몇 건을 더 봐야 함 (헤더가
같아도 의미가 다를 수 있음). 카테고리별 테이블 작업 시 하나씩 검증하면서 진행.

## title 카테고리 이상
`all_categories_fields.txt`에서 `title: (no attrs found)` — 다른 카테고리와 다른 레이아웃
가능성. 해당 카테고리 작업할 때 별도로 HTML 구조 확인 필요.

## 진행 순서
샘플을 이미 확인한 7개 카테고리(cannon/ship/recipe/consumable/tarotCard/cityNpc/quest)부터
전용 테이블을 만들고, 검증 후 나머지 63개로 확장. 전체를 한 세션에 끝내지 못할 수 있으므로
`checklist.md`에 진행 상태를 계속 반영.

## 2026-07-31 진행 결과 및 다음 세션을 위한 메모

**아키텍처 확정**: "획득 방법" 표는 카테고리 전용이 아니라 전체 사이트가 공유하는 컴포넌트임을
확인 (cannon 하나에서만 헤더 모양이 9가지). 그래서 스키마를 2층으로 나눔.
1. `item_*` 로 시작하는 공유 관계 테이블 (`build_acquisition.py`) — 모든 카테고리가
   공통으로 쓰는 "획득 방법", "변성연금", "종류/내용(필요·보상 등)" 패턴
2. 카테고리 전용 테이블 (`materialize_<category>.py`) — 그 카테고리만의 스탯 컬럼
   (예: cannon의 관통력/사정거리) + 관계 테이블 조인

**재사용 가능한 코드**: `build_acquisition.py`의 `parse_name_qty_pairs()`,
`split_multi_links()` 헬퍼는 "이름\n수량,\n이름\n수량" 셀 패턴과 "A,B,C" 멀티링크 셀 패턴을
다루는데, 카테고리 전용 스크립트에서도 그대로 재사용 가능 (import해서 쓰면 됨).

**남은 작업 규모**: `item_acquisition_unmapped`에 30,400행이 쌓여 있음. 이 중 상당수는
아직 안 다룬 "획득방법" 변형(예: 지역/장소/NPC, 종류/아이템, 지역/해역 — 헤더 모양 기준
정렬된 빈도는 `build_acquisition.py` 실행 결과 로그 참고)이고, 나머지는 ship의 기본성능/적재
같은 카테고리 자신의 스탯표라서애초에 공유 테이블 대상이 아님 — 각 카테고리 전용 스크립트를
만들 때 자연스럽게 처리됨.

**작업 방식 팁**: 새 카테고리를 다룰 때는
1. `raw_tables`에서 해당 카테고리 표 헤더 모양들을 먼저 나열해서 확인
2. 이미 있는 `item_acquisition_*`/`item_transmutation_*`/`item_detail_list`로 커버되는
   헤더 모양이면 그냥 조인해서 쓰면 됨 (별도 파싱 불필요)
3. 카테고리 고유의 스탯표(예: ship 기본성능)만 새로 매핑

**다음 후보**: 사용자가 자주 찾아볼 만한 카테고리(equipment, ship, recipe, consumable,
tradeGoods 등) 우선순위로 진행 추천. 전체 70개를 순서 상관없이 끝내야 하는 건 아니고,
필요한 것부터 채워나가는 방식도 가능 (Text-to-SQL은 테이블이 있는 만큼만 질의 가능).

## 2026-07-31 발견: "획득 방법" 탭 UI로 인한 스크래핑 데이터 누락

**증상**: 3단계(로컬 LLM 연동) 실사용 테스트 중 "해양조합 등록증을 해상 NPC로부터 얻을 수
있나?"를 물었더니 DB에 없다고 답함. 하지만 실제 사이트에는 "획득 방법" 섹션 안에
퀘스트/아이템 사용/해상 NPC 3개 탭이 있고, "해상 NPC" 탭에 함대 수/해역 표가 실제로 존재함.

**원인**: 사이트의 "획득 방법"이 React 클라이언트 사이드 탭 UI라서, `scraper.py`(순수 HTTP
GET)로 받은 원본 HTML에는 기본 활성 탭(대개 첫 번째)의 표만 들어있고 나머지 탭은 버튼
라벨만 있을 뿐 표 데이터 자체가 응답에 없음. 라이브 사이트를 직접 재요청해서 캐시가 오래된
게 아니라 사이트 자체가 이렇게 응답하는 것 확인(`함대 수` 헤더가 정적 HTML에 전혀 없음).
임베디드 JSON(`__NEXT_DATA__` 등)도 없어서 API 우회 경로도 없음 — 헤드리스 브라우저로 탭을
실제로 클릭해야만 데이터 확보 가능.

**영향 범위**: `border-b-2 px-2.5 py-1 text-[11px] font-semibold border-transparent
text-muted-foreground hover:text-foreground` 클래스(비활성 탭 버튼 전용)를 마커로 전체
스캔한 결과, 33,496건 중 **3,365건(약 10%)**에서 최소 1개 이상의 숨은 탭 확인. 카테고리별
집중도: consumable 848/2510, equipment 716/3453, tradeGoods 516/663, city 211/231(거의
전부), sea 126/127(거의 전부), field 231/563, cannon 136/566 등.

**해결**: `scrape_hidden_tabs.py` 신규 작성. Playwright(chromium)로 영향받는 항목만
방문해서 비활성 탭 버튼을 순서대로 클릭 → 매 클릭마다 `build_structured_db.extract_detail()`
재사용해서 페이지 스냅샷을 재파싱 → 기존 raw_tables/raw_attrs 시그니처(label+headers 또는
label+text)에 없는 것만 새 행으로 추가. `hidden_tabs_progress` 테이블로 진행상황 추적,
재실행 시 이미 처리한 URL은 자동 스킵.

**검증**: 10건 테스트 — cannon 5건에서 기존엔 못 보던 "레시피 책" 획득 경로(레시피/스킬/재료)
와 "해상 NPC"(함대 수/해역) 표가 정상 추가됨. `build_acquisition.py`의
`COVERED_HEADER_SHAPES`에 `("해상 NPC","함대 수","해역")` 매핑이 **이미 준비되어 있어서**
데이터만 채워지면 별도 파서 작업 없이 바로 `item_acquisition_marine_npc_sea` 등에 반영됨.

**완료 (2026-08-01)**:
1. ~~전체 배치 실행~~ — 첫 실행이 특정 항목에서 hang(프로세스는 살아있는데 CPU 사용량 0,
   몇 시간 정체)되어 발견 즉시 강제 종료. 원인 추정: Playwright 기본 타임아웃이 걸리지
   않는 엣지 케이스(다이얼로그 등). 개별 항목 45초 하드 데드라인 + 기본 타임아웃 10초 +
   200건마다 page 재생성으로 보강 후 재실행 → 전체 3,365건 완주(오류 0건,
   1,210건에서 신규 데이터 발견)
2. `build_acquisition.py` 재실행 완료 (DROP+재생성이라 안전 확인됨)
3. `materialize_generic.py`, `materialize_consumable.py`, `materialize_cannon.py` 재실행 완료
4. "해양조합 등록증"(item_id=1898) 재검증 완료 — `item_acquisition_marine_npc_sea`에
   78건 정상 반영, 사이트 스크린샷과 실제 매칭 확인. item_acquisition_marine_npc 전체
   4,352행, item_acquisition_marine_npc_sea 전체 5,980행으로 갱신됨

**참고**: `get_item_detail()` Tool 함수는 카테고리 전용 테이블(예: certificate)만 item_id로
조인하고, `item_acquisition_marine_npc_sea` 같은 공유 관계 테이블은 자동으로 안 붙여준다.
"해양조합 등록증을 해상 NPC로 얻을 수 있나" 같은 질문에 모델이 다시 잘 답하려면 결국
`run_sql`로 직접 조인해야 함 — 모델이 여전히 못 찾으면 get_item_detail을 확장해서
item_acquisition_* 계열을 자동으로 조인하는 개선이 다음 후보.
