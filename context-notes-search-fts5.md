# 기존 sqlite DB 검색 효율화 컨텍스트 노트

## 이전 세션 플랜 파일 관계
숫자 콤마 정제 작업 때 쓰던 `plan.md`/`checklist.md`/`context-notes.md`는
`plan-comma-format.md` 등으로 이름을 바꿔 보존함 (커밋은 이미 완료된 상태 —
`git diff HEAD` 없음 — 였고 체크리스트의 "기록" 항목 중 옵시디언 로그 append만
미완으로 남아있었으나 이번 작업과 무관해서 그대로 둠). 이번 파일들은 검색 효율화
작업 전용.

## 배경 대화 흐름
1. 처음엔 dolworld.notion.site를 챗봇 검색에 반영하는 요청으로 시작 →
   WebFetch로 확인해보니 클라이언트 사이드 렌더링(SPA)이라 정적 페치로는
   콘텐츠를 못 읽음(단순 "Notion" 텍스트만 반환됨).
2. 사용자가 대안으로 `http://gvo.gamedb.info/wiki/?FrontPage`(PukiWiki 기반
   일본판 大航海時代Online 팬위키) 제시 — `?cmd=list` 기준 약 1,900+ 페이지,
   EUC-JP 인코딩. 크롤링은 기술적으로 수월하지만 일본판이라 한국판과 데이터가
   다를 수 있음을 확인 후 사용자에게 크롤링 범위/방식(A: 전체 크롤링+로컬 인덱스
   vs B: 매 질문 실시간 조회) 질문.
3. 사용자가 SQLite의 RAG 지원 여부를 질문 → FTS5(키워드/BM25) vs sqlite-vec(벡터
   유사도) 설명, `node:sqlite`(`DatabaseSync`)가 `loadExtension()`을 지원해서
   기술적으로 sqlite-vec 연동도 가능함을 확인.
4. **사용자가 외부 사이트 크롤링 자체를 보류하고, 기존 `dho_structured.sqlite3`
   검색/관리 효율화로 방향 전환** — 이번 plan.md는 이 요청에 대응.

## 조사 결과 (실측)
- `items_core`: 33,496행, PK(category, item_id), `name`/`title`에 별도 인덱스 없음.
- `EXPLAIN QUERY PLAN SELECT ... FROM items_core WHERE name LIKE '%검%' OR title LIKE '%검%'`
  → `SCAN items_core` (leading wildcard라 인덱스 있어도 못 씀). 실측 ~36ms.
- 명시적 인덱스는 3개뿐: `idx_raw_attrs_item`, `idx_raw_tables_item`
  (둘 다 `(category, item_id)`), `idx_item_backlinks_target`
  (`(target_category, target_item_id)`) — 전부 상세조회용 조인 인덱스,
  검색(search_items 등)용 인덱스는 전무.
- `sqlite_stat1` 테이블 없음 → `ANALYZE` 실행된 적 없음.
- `raw_attrs` 149,381행, `raw_tables` 58,584행, `item_backlinks` 440,926행,
  `item_detail_list` 99,800행 — description/raw_attrs 쪽 텍스트양이 상당해서
  FTS5로 커버하면 검색 recall이 크게 늘어날 것으로 판단.
- (지나가며 확인) `items_core.description` 등 한글 텍스트는 실제로 정상 UTF-8
  인코딩 상태 — Bash 도구 콘솔에서 `print(repr(...))`로 볼 때만 codepage 문제로
  깨져 보였을 뿐, `.encode('utf-8')`로 확인하면 정상 한글. 인코딩 버그 아님
  (기존 메모리 [[encoding_bug_fixed]]와 일치, 재발 아님 — 착오였음, 기록만 남김).

## 설계 결정 (진행 중, 구현 전)
- FTS5를 1순위로 채택(사용자와의 직전 대화에서 "임베딩 API 비용 없이 바로 되는
  FTS5부터 시작 → 필요시 sqlite-vec 추가"로 의견 제시했고 사용자가 이어서
  "기존 DB 효율화"로 화제를 좁혔으므로, 이 우선순위를 그대로 유지).
- 커넥션 재사용/스키마 캐시/ANALYZE는 FTS5와 별개로 독립적인 개선이라 같이
  진행 — 코드 변경 리스크가 낮고(SQL 문자열/커넥션 라이프사이클 변경만) 효과가
  분명함.

## 중간에 나온 별도 논의 (구현과 무관, 기록만)
FTS5 착수 직전에 사용자가 "DB를 Supabase에 올리는 건 어떨까"(하이브리드
검색/백업/관리 목적)를 질문 → 실측(현재 DB 256MB, Supabase 무료 500MB로 여유
부족, 챗봇이 한 턴에 도구를 최대 8번 호출하는데 네트워크 왕복 비용 발생 등) 근거로
당장은 비추천하고 Turso(SQLite 호환, 무료 5GB)를 대안으로 제시함. 사용자가 이
논의는 보류하고 "일단 FTS5 넓은 범위로"로 되돌아옴 — 이번 구현은 로컬
`dho_structured.sqlite3` 파일 기준으로 진행. Turso로 나중에 옮기더라도 SQL
방언이 거의 같아서(libSQL) 이번 FTS5 스키마/쿼리가 그대로 재사용 가능할 것으로
예상(미검증).

## 구현 결정 (완료)
- **범위**: `items_core`(name/title/description) + `raw_attrs`(item당 label+text를
  `GROUP_CONCAT(label || ' ' || text, ' ')`로 이어붙인 `attrs_text` 컬럼) 둘 다 포함 —
  사용자가 "넓게"로 확정.
- **토크나이저**: `trigram` 채택. 이유: 기존 UX가 `LIKE '%keyword%'`(부분일치)라서,
  단어 경계 기반 토크나이저(unicode61 등)로 바꾸면 "부분일치"라는 기존 동작이
  깨짐. trigram은 진짜 부분일치(인덱스 기반)를 지원해서 기존 UX를 유지하면서
  속도만 개선하는 목표에 부합.
- **구문(phrase) 쿼리 강제**: MATCH에 넘기는 문자열을 항상 큰따옴표로 감싼다
  (`ftsPhrase()`). 실측으로 확인한 이유 두 가지.
  1. 안 감싸면 공백이 포함된 키워드("조합 등록")가 FTS5 문법상 `조합 AND 등록`으로
     쪼개져 해석됨 — "조합 등록"이라는 연속 문자열 매치가 아니게 됨.
  2. 사용자가 입력한 키워드에 `AND`/`OR`/`NOT`/`"` 같은 FTS5 예약 문법이 섞여
     있으면(예: 아이템 이름에 실제로 이런 단어가 들어갈 수 있음) 검색 문법으로
     오인식되어 에러나거나 의도와 다른 결과가 나올 수 있음 — phrase로 감싸면
     리터럴 텍스트로 처리되어 안전.
- **3글자 미만 폴백**: trigram은 최소 3글자부터 인덱싱 가능(SQLite 자체 제약,
  실측으로 확인 — "갑옷"/"조합"/"검" 같은 2글자 이하 쿼리는 trigram MATCH가
  항상 0건 반환). 한국어 단어가 2글자인 경우가 흔해서(예: "갑옷") 이 케이스를
  놓치면 안 됨 → `[...keyword].length < 3`이면 기존 `LIKE` 쿼리로 자동 폴백.
- **공유 헬퍼로 통합**: `search_items`/`get_item_detail`/`get_backlinks` 세 곳이
  전부 "키워드로 후보 항목 찾기"라는 동일한 로직을 각자 구현하고 있었어서,
  FTS5 교체 김에 `findMatchingItems(db, keyword, limit)` 하나로 통합(중복 3군데
  → 1군데). 단, `get_item_detail`은 원래 최상위 결과에 `description`을 포함했는데
  공유 헬퍼는 `category/item_id/name/title`만 반환하도록 설계해서(다른 두 함수는
  description이 필요 없었으므로), `get_item_detail`에서만 별도로 PK 조회
  (`WHERE category=? AND item_id=?`, `items_core` PK라 O(1))로 description을
  보충해 기존 출력 형태를 그대로 유지함.
- **빌드 스크립트 위치**: `build_search_index.py` 신규, 기존 `build_backlinks.py`
  스타일(DHO_DB_PATH 환경변수, DROP+CREATE, print 진행상황) 그대로 따름.
  `dho_webapp.py`의 `DERIVED_PIPELINE_SCRIPTS` 리스트 맨 끝에 추가 — 원본
  데이터가 바뀌어도(웹앱에서 항목 저장 등) 검색 인덱스가 항상 최신 상태로
  같이 재생성됨.

## 실측 검증 결과
- 인덱스 빌드: 33,496건(items_core 전체) 적재 확인.
- 속도: "카노푸스"(4글자) 기준 LIKE 15.6ms vs FTS MATCH 0.8ms — 약 20배.
- Recall 개선 실증: raw_attrs에만 존재하는 값(aide/14497의 한 속성값, name/title엔
  없음)으로 검색 시 — 기존 LIKE(name/title만 검색)는 해당 항목을 못 찾지만
  FTS MATCH(attrs_text까지 포함)는 정상적으로 찾음. 즉 "이름에 없는 단어로는
  못 찾는다"는 원래 문제가 해결됨.
- `node --experimental-strip-types`로 `chat/lib/dho-db.ts`의 실제 export 함수를
  직접 호출해 종단 검증: `searchItems('카노푸스')` FTS 경로 정상, `searchItems('갑')`
  1글자 폴백 정상, `getItemDetail('해양조합 등록증')`가 7건 매치 + description +
  detail + 획득_방법(acquisition)까지 기존과 동일하게 반환됨을 확인
  (해양조합 등록증 케이스는 NEXT_STEPS.md에도 기록된 기존 회귀 테스트 케이스).
- `npm run lint`/`npm run build`(chat) 통과. `dho_webapp.py` Flask test_client로
  `/`, `/certificate`, `/certificate/1898` 200 확인 — `DERIVED_PIPELINE_SCRIPTS`에
  스크립트 하나 추가한 것 외 webapp 로직은 안 건드렸으므로 회귀 없음.
- (지나가며 재확인) 처음엔 "기사"(2글자) 테스트에서 FTS가 0건이라 버그로
  오인했으나, 3글자 미만이라 trigram이 애초에 인덱싱 못 하는 케이스였음 —
  실제 버그 아니었음(위 3글자 미만 폴백 설계로 해결됨).

## 미해결 / 다음 라운드
- 커넥션 재사용(`chat/lib/dho-db.ts` 모듈 레벨 싱글턴), `acquisitionInfo()` 스키마
  캐시, `ANALYZE` 추가는 이번 요청 범위(FTS5)에 안 들어가서 보류 — 사용자가
  원하면 다음 라운드로.
- `openwebui_tool_dho_sql.py`(레거시)에 동일 FTS5 검색을 반영할지 — 보류.
- Supabase/Turso 마이그레이션 논의는 완전히 별개 트랙으로 보류 중.
