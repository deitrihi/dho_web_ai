# 2단계 체크리스트

## 0. 준비
- [x] 원본 HTML 인코딩 버그 발견 및 복구 (`dho_cache.sqlite3` 정상화)
- [x] 70개 카테고리 샘플 1건씩 속성/표 구조 추출 (`all_categories_fields.txt`)

## 1. 범용 추출기 + 스테이징 (완료 2026-07-31)
- [x] `build_structured_db.py`: 상세 페이지 HTML → `{title, description, attrs, tables}` 파싱 함수
- [x] `dho_structured.sqlite3` 생성: `items_core`(category,item_id,name,title,description,url)
- [x] 스테이징 테이블: `raw_attrs`(category,item_id,label,text,links_json),
      `raw_tables`(category,item_id,label,headers_json,rows_json)
- [x] 전체 33,496건에 대해 범용 추출 실행 — 33,496건 성공, 실패 0건

## 2. 공유 획득방법/관계 테이블 (완료 2026-07-31, `build_acquisition.py`)
"획득 방법" 표가 카테고리 무관하게 같은 헤더 모양을 반복하는 것을 확인 (cannon 하나에서만
9가지 형태 발견). label이 아니라 헤더 모양으로 판별해서 전체 카테고리에 공통 적용.

- [x] `item_detail_list` (종류/내용 2열 표 — 필요/보상/연결된장소 등 다수 섹션이 공유하는
      가장 흔한 모양) — 99,800행 매핑
- [x] `item_transmutation_policy/skill/material` (변성연금 + 획득방법 내 변성 패턴 통합,
      정책당 스킬/재료를 별도 연결테이블로 분리 — 교차곱 방지) — 정책 22,409 / 스킬 44,817 / 재료 67,221행
- [x] `item_acquisition_seller` (판매 NPC/지역/장소) — 13,807행
- [x] `item_acquisition_recipe` + `_skill` + `_material` (레시피책/레시피/스킬/재료) — 1,353/1,732/3,689행
- [x] `item_acquisition_from_item` (아이템 단일 목록) — 6,241행
- [x] `item_acquisition_npc_location` (지역/도시/도시 인물) — 466행
- [x] `item_acquisition_marine_npc` + `_sea` (해상 NPC/함대수/특징/해역) — 177/334행
- [x] `item_acquisition_quest`, `item_acquisition_treasuremap` — 19/3행
- [x] 미매핑 표는 `item_acquisition_unmapped`에 원본 보존 (30,400행 — 아직 다루지 않은
      획득방법 변형 + 카테고리 전용 스탯표들이 섞여 있음, 아래 3번 참고)

## 3. 카테고리별 전용 테이블 (전체 70/70 완료 — 4개 수작업 + 66개 자동화, 2026-07-31)

**수작업 4개**(cannon/recipe/consumable/tarotCard)는 원본 대조 검증까지 완료, 컬럼명 영어
번역, 관계 데이터 정밀 분리(교차곱 방지 등).

**자동화 66개**(`materialize_generic.py`)는 원본 한글 라벨을 컬럼명으로 그대로 사용,
숫자/링크 자동 판별. `ship`/`equipment`/`city` 샘플 대조 검증 결과 원본과 정확히 일치
확인. 알려진 한계.
- 숫자에 쉼표가 섞인 값(예: 선박 내구도 "1,183")은 INTEGER 자동판별에서 제외되어 TEXT로 남음
- 셀에 링크가 2개 이상이면 첫 번째만 외래키로 잡음 (전체 텍스트는 `_text` 컬럼에 보존됨)
- 필요시 특정 카테고리만 골라서 `materialize_cannon.py`처럼 손으로 다시 다듬을 수 있음
  (원본 데이터는 raw_attrs/raw_tables에 그대로 있어 재크롤링 불필요)

DB 전체 테이블 수: 211개 (`dho_structured.sqlite3`)

<details>
<summary>이전 진행 기록 (자동화 이전)</summary>
- [x] `cannon` — 스탯 8컬럼(분류/포탄종류/내구도/관통력/사정거리/포탄속도/작렬범위/장전속도)
      + 위 공유 관계 테이블 연결로 검증 완료 (`materialize_cannon.py`, 566건)
- [x] `recipe` — 분류/레시피책 + `recipe_product`(생산품) 전용 테이블, "필요"는
      공유 `item_detail_list`에서 조회 (`materialize_recipe.py`, 3,045건 검증 완료)
- [x] `consumable` — 분류/사용효과, 획득방법은 전부 공유 테이블(판매NPC/레시피/직접판매)로
      커버됨, 전용 관계 테이블 불필요 (`materialize_consumable.py`, 2,510건 검증 완료)
- [x] `tarotCard` — 효과/요약만 전용 컬럼, 입수NPC는 공유 `item_acquisition_npc_location`이
      헤더 모양만으로 자동 처리 (전용 코드 없이 커버됨) (`materialize_tarotcard.py`, 22건 검증 완료)
- [x] 공유 테이블에 `item_acquisition_directsale`(판매기간/수량/가격) 추가 — consumable 등에서 사용
- [ ] `ship` — 다중 스탯표(기본성능/적재/강화상한/부품/데코/스킬)는 "획득방법"류가 아니라
      아이템 자신의 속성이라 공유 테이블 대상이 아님. ship 전용 스크립트 필요
- [ ] `cityNpc`, `quest` — 샘플 구조 확인 완료(`summary_*.txt` 참고), 전용 테이블 미작성
- [ ] 나머지 65개 카테고리 — `all_categories_fields.txt` 기준으로 그룹핑해서 순차 진행.
      `item_acquisition_unmapped`에 쌓인 나머지 획득방법 변형(지역/장소/NPC,
      종류/아이템, 지역/해역, 유형/획득방법/종류/아이템 등)도 이어서 공유 테이블에 추가 가능
</details>

## 4. 검증
- [x] cannon/recipe/consumable/tarotCard: 원본 HTML과 대조해서 값 정확히 일치 확인
- [x] 자동화 66개: 대표 샘플(ship/equipment/city) 대조 검증 — 일치 확인
- [ ] 나머지 카테고리는 필요할 때 개별적으로 원본 대조 검증 (전수 검증은 안 함)

## 5. 마무리 (다음 세션 — 3단계로 넘어가기 전)
- [ ] 스키마 문서화 (211개 테이블/컬럼 설명 — Text-to-SQL 프롬프트에 넣을 요약)
- [ ] 자동화로 남은 정밀도 이슈(쉼표 포함 숫자 TEXT 처리 등) 필요한 카테고리만 선별 개선
- [ ] `item_acquisition_unmapped`(약 3만 행)에 남은 패턴 계속 정리 여부 판단
