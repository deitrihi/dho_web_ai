# 챗봇 역방향 조회 도구(get_backlinks) 추가

## 요청
- "이런식으로 너무 많이 검색이 이루어지는것 같은데 해결 방법이 있을까?" (스크린샷: "퀘스트의
  보상 아이템중에 발주서를 가장 많이 주는 퀘스트 10개만 정리해줘" 질문에 도구 호출 15개
  이상 쌓이고도 "도구 호출 한도에 도달해 답변을 끝맺지 못했습니다" 경고로 종료)
- 원인/해결 방향 설명 후 "추가해줘"로 진행 확정.

## 원인
- 이 질문은 역방향 조회("발주서를 참조하는 퀘스트")인데, 챗봇 도구는 전부 정방향(이 아이템
  자신의 획득처)만 다룸 — `get_item_detail`의 "획득_방법"은 `item_acquisition_*`/
  `item_detail_list`를 category+item_id(자기 자신)로 조인해서 채우므로, 발주서를
  "보상으로 주는" 퀘스트(= 발주서가 content_item_id로 걸려있고 quest가 category/item_id인
  행)는 안 잡힘.
- 모델이 이걸 몰라서 find_tables/get_table_schema/run_sql로 item_acquisition_quest,
  item_acquisition_from_item, item_acquisition_unmapped 등을 순서대로 찔러보며 맨땅에서
  탐색 — 스텝 예산(16)을 다 쓰고도 못 찾음.

## 조사
- `item_detail_list` 스키마 확인: `category, item_id, source_label, type_text,
  content_name, content_category, content_item_id` — quest 보상은
  `category='quest', source_label='보상', content_category/content_item_id`가 보상
  아이템을 가리킴(역방향). 정방향 조회(get_item_detail)로는 못 찾는 이유가 여기서 확인됨.
- `item_backlinks`(build_backlinks.py, 웹앱 "이 항목을 참조하는 곳" 섹션의 데이터 소스)가
  이미 이 역방향 관계를 전부 인덱싱해뒀음을 확인 — raw_tables/raw_attrs의 정방향 링크를
  전부 스캔해서 뒤집은 테이블이라 quest의 "보상" 표에서 발주서로 가는 링크도 포함됨.
  실제 쿼리로 검증: `item_backlinks WHERE target=발주서 AND source_category='quest' AND
  source_label='보상'` — quest별 backlink 확인됨.

## 행동
- `chat/lib/dho-db.ts`: `getBacklinks(keyword)` 신규. 키워드로 items_core를 먼저 검색해서
  후보를 찾고(`get_item_detail`/`search_items`와 같은 패턴), 각 후보에 대해
  `item_backlinks`를 `source_category`별로 그룹핑한 개수 + 항목 목록(카테고리당 최대
  50건, 웹앱의 `BACKLINKS_PER_CATEGORY=30`보다 조금 넉넉하게)을 반환.
- `chat/app/api/chat/route.ts`: `get_backlinks` 도구로 등록(`get_item_detail` 바로 다음
  순서). 설명에 "'이 아이템을 보상으로 주는 퀘스트' 같은 역방향 질문에 사용,
  get_item_detail은 반대 방향이라 못 씀"을 명시. 시스템 프롬프트에도 "역방향 질문은
  get_backlinks를 바로 쓰고 item_acquisition_*/item_detail_list를 맨땅 탐색하지
  말라"는 문장 추가.

## 검증
- `node --experimental-sqlite`로 실제 `dho_structured.sqlite3`에 대고 `getBacklinks`와
  동일한 쿼리를 직접 실행 — "발주서" 키워드로 10개 아이템 매칭, 각각 quest backlink
  138건/104건 등 정상 반환 확인(반환 목록은 50건으로 캡, 총 개수는 `count`로 별도 확인
  가능).
- `npm run build`/`npm run lint` 통과.

## 미해결
- 실제 LLM으로 "발주서를 가장 많이 주는 퀘스트 10개" 질문을 다시 던져서 이번엔
  get_backlinks 한 번으로 스텝을 아끼고 답을 완성하는지는 API 키가 없는 이 환경에서
  재현 못 함 — 사용자가 같은 질문으로 재시도해서 확인 필요.

## 추가: 수량(qty) 미표시 문제 (같은 세션, 사용자 지적)

### 요청
- "질문의 중요한 포인트는 발주서를 몇개가 주는 것일 텐데, 수량을 보여주지 않는다고 하니
  좋지 않은거 같아" — 위 미해결 항목("수량까지는 안 알려줌")을 명시적으로 지적.

### 조사
- `item_detail_list.content_name`이 애초에 수량을 안 담고 있는 이유를 raw 데이터로 확인.
  `raw_tables`의 실제 셀 텍스트는 `"구입 발주서(카테고리 1) 5"`처럼 링크 텍스트 뒤에
  수량이 그대로 붙어있는데, `build_acquisition.py`의 `split_multi_links()`가 링크가
  있는 셀은 링크의 표시 텍스트("구입 발주서(카테고리 1)")만 취하고 뒤에 붙은 숫자를
  버려서 `item_detail_list`엔 애초에 수량이 없음 — Python 파이프라인의 데이터 손실
  버그. `run_sql`로 `item_detail_list`를 직접 조회해도 동일하게 안 보임.
- 두 가지 해결 경로 검토: (a) `build_acquisition.py`를 고쳐서 `item_detail_list`에 qty
  컬럼을 추가하고 245MB DB를 재빌드(근본 수정이지만 프로덕션 DB를 건드리는 더 큰
  작업), (b) chat 쪽에서만 원본 `raw_tables` 셀 텍스트를 다시 파싱해서 복구(DB는 안
  건드림, 범위가 이번 요청에 맞게 작음). 이번엔 (b)로 진행 — DB 재빌드는 웹앱/배포에도
  영향이 있는 더 큰 작업이라 범위를 넘어선다고 판단.

### 행동
- `chat/lib/dho-db.ts`: `extractQuantity(cellText, linkText)` — 셀 텍스트가 링크 텍스트로
  시작하면 그 뒤 남는 부분이 숫자인지 확인해서 수량으로 추출(아니면 null, 아이템 이름
  자체에 숫자가 들어간 경우 오탐 방지). `attachQuantities()` — backlink 항목과 같은
  (category,item_id,label) 키로 `raw_tables`를 배치 조회(항목별 개별 쿼리 대신 그룹당
  1쿼리)해서 대상 아이템으로 가는 링크가 있는 셀에서 수량을 뽑아 `entries`에 `qty`로 붙임.
- 정렬 버그도 같이 발견/수정: 기존엔 SQL에서 `source_item_id` 순으로 앞 50건만 잘라온
  뒤 qty를 계산해서, 진짜 최댓값이 잘린 50건 밖에 있으면 놓쳤음(실측: 잘림 없이 계산한
  진짜 최댓값은 59인데, 정렬 없는 50건 안에서는 최대 22로만 보임). SQL 단계 cap을
  `RAW_ENTRY_FETCH_CAP=500`으로 올리고, qty 계산 후 내림차순 정렬 → `ENTRY_OUTPUT_CAP=50`
  으로 최종 컷하도록 순서를 바꿈.
- `route.ts`: 도구 설명에 "entries는 이미 qty 내림차순 정렬이니 '가장 많이 주는' 질문은
  재정렬 없이 앞쪽만 쓰면 됨" 추가.

### 검증
- `node --experimental-sqlite`로 실제 DB에 대고 "발주서" 전체 변형(4개 아이템)의 quest
  backlink를 합산 재현 — 상위 10개가 실제 최댓값(59/56/56/55/55/55/54/54/52/52)으로
  정확히 나오는 것 확인(수정 전엔 정렬 없는 50건 안에서 최대 22로만 보였던 것과 대조).
- `npm run build`/`npm run lint` 통과.

### 미해결
- `item_detail_list` 테이블 자체의 수량 손실은 여전히 남아있음(이번엔 chat 쪽에서만
  raw_tables를 재파싱해서 복구했고, DB/파이프라인은 안 건드림) — 다른 소비자(직접 SQL
  분석, 웹앱 등)가 `item_detail_list.content_name`으로 수량을 기대하면 여전히 못 봄.
  필요해지면 `build_acquisition.py`의 `split_multi_links()`를 고치고 DB를 재빌드하는
  근본 수정을 별도로 검토.
- 실제 LLM 재현 검증은 API 키 없는 환경이라 못함(사용자 재시도 필요).
