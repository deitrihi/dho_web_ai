# item_detail_list 수량(content_qty) 근본 수정

## 요청
- 지난 세션에 chat의 `get_backlinks`에 수량(qty)을 raw_tables 재파싱으로 임시 복구했던
  것에 이어, 사용자가 "item_detail_list에 수량을 반영하는 건 얼마나 걸릴까?"라고 질문 →
  간단한 소요 추정 후 "진행해줘"로 확정.

## 배경(지난 세션에서 이미 확인된 원인)
- `build_acquisition.py`의 `split_multi_links()`가 "종류/내용" 표(필요/보상 등 다수
  섹션이 공유)의 내용 셀에서 링크가 있으면 링크 텍스트만 취하고, 원본 셀 텍스트에 붙어있는
  수량/랭크("탐색 1, 고고학 2, 이탈리아어 1"의 1/2/1, "구입 발주서(카테고리 1) 5"의 5)를
  버려서 `item_detail_list`에 애초에 수량이 없었음.

## 사전 조사 (구현 전 패턴 검증)
- 전체 DB의 "종류/내용" 표(19,376개 표, 22,717개 링크 셀)를 스캔해서 수량 구분자 패턴을
  확인.
  - 콤마로 나눈 세그먼트 수와 링크 수가 일치 + 각 세그먼트가 링크 텍스트로 시작 → 뒤에
    남는 게 숫자면 수량(공백 구분, "\n" 구분 아님 — 기존 `parse_name_qty_pairs()`가
    쓰던 "\n" 패턴과는 다른 표 모양이라 재사용 불가, 새 함수 필요).
  - 세그먼트/링크 수 불일치: 1,895건(8.3%) — 던전/퀘스트 "필요"에 연결된 퀘스트 설명이
    자유 텍스트로 섞인 예외 케이스(예: "[ 종교건축물 ] 1 기자 피라미드 < 모험 | ... >").
  - 세그먼트가 링크 텍스트로 시작 안 함: 747건(3.3%) — 링크 앞에 다른 텍스트가 있는 케이스.
  - 나머지 약 88%는 안전하게 수량 추출 가능.

## 행동
- `build_acquisition.py`:
  - `item_detail_list` 스키마에 `content_qty INTEGER` 컬럼 추가.
  - `split_multi_links_with_qty()` 신규 함수 — 위에서 확인한 패턴대로, 세그먼트/링크
    수가 일치하고 접두어가 맞을 때만 수량을 신뢰해서 추출, 안 맞으면(약 12%) 기존
    `split_multi_links()`와 동일하게 수량 없이 이름만 반환(회귀 없음). 기존
    `split_multi_links()`는 다른 3곳(item_acquisition_seller 등, 수량 개념 없음)에서
    그대로 쓰므로 안 건드림 — "종류/내용" branch(item_detail_list 전용)에서만
    `split_multi_links_with_qty()`로 교체.
  - INSERT 문에 `content_qty` 추가.
- `build_acquisition.py` 재실행으로 `item_detail_list` 재생성(스키마 변경이라 DROP+재생성,
  기존 관례).

## 검증
- 총 행 수 99,800건 불변(컬럼만 추가, 데이터 손실 없음) 확인.
- `content_qty IS NOT NULL` 31,640건 — 사전 조사에서 측정한 "공백+숫자로 수량 매칭"
  개수(31,640)와 정확히 일치.
- 지난 세션에 직접 확인했던 케이스 3개로 재검증.
  1. quest 16029 보상: "구입 발주서(카테고리 1)" content_qty=5 — 원본 셀 텍스트("구입
     발주서(카테고리 1) 5")와 정확히 일치.
  2. quest 15390 필요: 탐색=1, 고고학=2, 이탈리아어=1 — 원본("탐색 1, 고고학 2,
     이탈리아어 1")과 정확히 일치.
  3. quest 15399 필요(예외 케이스, 연결된 퀘스트 설명이 섞인 지저분한 셀): 크래시 없이
     모든 행이 content_qty=NULL로 안전하게 폴백, 기존 동작(이름만 보존)과 동일 — 오탐
     없음 확인.
  4. "발주서 top10 (전체 변형 통합, 수량 내림차순)" 쿼리를 `item_detail_list`에 직접
     날려서 지난 세션 chat 쪽 임시 로직(raw_tables 재파싱)이 냈던 것과 정확히 같은 결과
     (59/56/56/55/55/55/54/54/52/52) 재현 확인 — 두 구현이 같은 원본 데이터를 놓고 같은
     답을 낸다는 교차검증.
- chat 코드 변경 없이도 `chat/lib/dho-db.ts`의 `acquisitionInfo()`가 `SELECT *`라서
  `content_qty`를 자동으로 돌려주는 것 확인(node:sqlite로 quest 15390 직접 조회) —
  즉 이제 chat에서 "이 퀘스트에 필요한 스킬 랭크"류 질문에 `get_item_detail` 한 번으로
  수량까지 바로 보임.
- 지난 세션에 만든 `rebuild_derived_tables()`(webapp 저장 트리거) 전체 파이프라인을
  다시 돌려서 다른 파생 테이블들(item_backlinks 440,926 / cannon 566 / recipe 3,045 /
  consumable 2,510 등) 전부 회귀 없이 그대로인 것 확인, 에러 0건.
- Flask test_client로 `/`, `/quest`, `/quest/15390`, `/cannon`, `/cannon/new`,
  `/assistant` 200 재확인.

## 미해결 (다음 후보, 이번엔 손 안 댐)
- chat의 `get_backlinks`(`attachQuantities`/`extractQuantity`, raw_tables 직접 재파싱)는
  이제 `item_detail_list.content_qty`와 로직이 중복됨 — "종류/내용" 표에서 온 backlink는
  `item_detail_list`를 (category=source_category, item_id=source_item_id,
  source_label=source_label, content_category/content_item_id=target) 키로 조인해서
  가져오는 쪽으로 단순화할 수 있음. 이번 요청 범위(파이프라인 수정)를 벗어나서 손 안 댔고,
  현재 chat 쪽 구현도 여전히 정상 동작하므로 급하지 않음.
- `tarot_card`/`tarotCard` 테이블명 불일치(지난 세션 발견, 미해결 그대로 유지).
