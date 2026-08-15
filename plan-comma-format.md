# 숫자 콤마 텍스트 컬럼 정제 + 콤마 포맷팅 메소드 추가

## 목표
`dho_structured.sqlite3`의 파생 테이블 중 일부 숫자 컬럼이 원본 크롤링 데이터의 천단위
콤마("1,500") 때문에 정수 판별 정규식과 fullmatch가 안 되어 TEXT로 저장되고 있다. 이걸
콤마를 제거한 뒤 INTEGER로 저장하도록 파이프라인을 고치고, 기존 DB도 재생성한다.
그리고 챗봇(`run_sql`)이 숫자 값을 사람이 읽을 때 다시 세자리마다 콤마를 붙여 보여줄 수
있도록 포맷 메소드를 만든다.

## 조사 결과 요약
- **원인 1** (`materialize_generic.py:60,64,101` `build_category_table`): `FULL_INT_RE`가
  콤마 포함 문자열과 fullmatch 안 됨 -> 컬럼이 TEXT로 생성되고 원문 그대로 저장.
  영향: `courtRank.명성`, `discovery.*`, `ganador.*`, `research.필요 페이지` 등
  자동 생성 카테고리 테이블(92개) 다수.
- **원인 2** (`materialize_generic.py:132-137` `build_relation_tables`): `{header}_text`
  컬럼이 숫자 판별 없이 무조건 TEXT로 고정 생성. 영향: `city__판매 아이템`,
  `sellerNpc__판매 아이템`, `portPermit__명성`, `ship__기본 성능`/`ship__적재` 등.
- **별도 버그** (`materialize_cannon.py:134`): `re.search(r"-?\d+", text)`가 콤마에서
  멈추는 첫 숫자 런만 잡아서 "1,032" -> **1**로 잘못 저장됨(콤마 문제보다 심각한 데이터
  손상). `cannon` 테이블 6개 INT 컬럼 중 실제 영향은 `관통력`(penetration)만 확인됨
  (raw_attrs 전수 스캔 완료, cannon/recipe/consumable/tarotCard 4개 handcrafted 카테고리
  중 콤마 포함 값은 cannon.관통력이 유일).
- **비교 참고**: `build_acquisition.py:410,416`의 `price_krw`는 이미
  `re.search(r"[\d,]+", ...).replace(",", "")`로 콤마를 올바르게 제거하는 정상 사례.
- **화면 출력**: `dho_webapp.py`는 파생 테이블(cannon 등 211개)을 전혀 읽지 않고
  `raw_attrs`/`raw_tables` 원문을 그대로 렌더링(`templates/item.html`) — 원본 그대로라
  이미 콤마가 있고 수정 대상 아님. 숫자를 실제로 "표기"하는 지점은 챗봇의 `run_sql`
  결과(JSON)뿐 — `openwebui_tool_dho_sql.py`(Python, OpenWebUI 플러그인 원본)와
  `chat/lib/dho-db.ts`(TypeScript 포팅본) 두 곳.

## 사용자 결정 사항
- 포맷 메소드는 챗봇 `run_sql`/`runSql` 결과에 연결한다.
- `materialize_cannon.py`의 별도 절단 버그도 이번에 같이 고친다.

## 접근 방식
1. **파이프라인 수정**
   - `materialize_generic.py`: 콤마 제거 헬퍼 추가 후 `build_category_table`의 정수 판별/삽입에
     적용. `build_relation_tables`는 헤더별로 값을 먼저 모아 숫자 여부를 판별하고(2-pass),
     전부 숫자면 `{header}_num INTEGER`(콤마 제거 후 저장), 아니면 기존처럼
     `{header}_text TEXT`로 생성.
   - `materialize_cannon.py`: INT_COLUMNS 파싱 시 콤마 제거 후 정규식 매칭.
2. **기존 DB 재생성**: 수정 전 `dho_structured.sqlite3` 백업 후, `dho_webapp.py`의
   `rebuild_derived_tables()`와 동일한 순서(build_backlinks -> build_acquisition ->
   materialize_generic -> materialize_cannon -> materialize_recipe -> materialize_consumable
   -> materialize_tarotcard)로 7개 스크립트를 직접 재실행.
3. **콤마 포맷 메소드 추가**
   - `openwebui_tool_dho_sql.py`: `format_number(value)` 함수 추가, `run_sql` 반환 직전
     각 row에 적용. `item_id`/`row_index`/`position`/`*_id` 같은 식별자 컬럼은 수량이
     아니므로 포맷 제외(콤마 붙이면 오해 소지).
   - `chat/lib/dho-db.ts`: 동일 로직을 `formatNumber()`로 포팅해 `runSql`에 적용
     (파일 상단 주석에 "openwebui_tool의 함수를 그대로 포팅"이라 명시되어 있어 관례 유지).

## 검증
- 재생성 전/후 `courtRank.명성`, `city__판매 아이템`, `cannon.penetration` 등 콤마
  케이스였던 값들이 올바른 정수로 들어갔는지 직접 SELECT로 대조.
- `cannon.penetration`이 더 이상 "1" 같은 잘린 값이 아니라 원래 값(1032 등)인지 확인.
- 전체 테이블 행 수가 재생성 전/후 동일한지(데이터 유실 없음) 확인.
- `run_sql`/`runSql`로 콤마 포함이었던 컬럼을 조회해 `"1,500"` 형태로 반환되는지,
  `item_id` 등 식별자 컬럼은 그대로(포맷 안 됨) 반환되는지 확인.
- webapp: `python dho_webapp.py`로 기존 라우트(`/`, `/cannon`, `/cannon/<id>`, `/assistant`)
  200 확인(파생 테이블 미사용 경로라 회귀 없어야 함, 확인 차원).
- chat: `npm run build`, `npm run lint` 통과.
