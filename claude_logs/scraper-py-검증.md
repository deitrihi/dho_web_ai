# 세션 로그 — scraper.py 검증

## 2026-07-30 | scraper-py-검증

### 요청
- scraper.py를 아직 실행하지 않은 상태에서, 실행 전 코드가 올바른지 검사해달라는 요청

### 행동
- README.md 확인 (이전 턴)
- scraper.py 전체 코드 리뷰
- `python -m py_compile scraper.py`로 문법 검사 → 통과
- Python 버전 확인 (3.14.5, `list[str] | None` 문법 호환)
- requests/bs4 미설치 확인 (README 설치 안내와 일치, 문제 아님)

### 결정
- 정적 리뷰 결과 발견된 이슈를 사용자에게 보고, 수정 여부는 사용자 판단에 맡김

### 후속 조치 (2026-07-30, 같은 세션)
- 사용자가 수정 적용 요청 → `get_max_page()`(L164), `crawl_category_list()`(L183)에서
  `category`를 `re.escape(category)`로 감싸도록 수정
- `python -m py_compile`로 재검사 → 통과
- CHANGELOG.md 신규 생성, `[미커밋]` 섹션에 항목 추가

### 실제 테스트 실행 (2026-07-30, 같은 세션)
- `pip install requests beautifulsoup4` 설치
- `python scraper.py discover` → 카테고리 70개 발견 (README 예상치와 일치)
- `python scraper.py crawl-lists --categories tarotCard` → 22건 수집 (README 예상치와 일치)
- `python scraper.py status` → tarotCard: 예상 22 / 목록완료 O / 수집됨 22 / 상세완료 0 → 정상
- 결론: 파싱 정규식이 실제 사이트 구조와 맞음을 확인. `dho_cache.sqlite3` 생성됨 (캐시 페이지 2건)

### 전체 목록 크롤링 (2026-07-30, 같은 세션)
- `python scraper.py crawl-lists --all` 실행 (백그라운드) → 70개 카테고리 전부 완료
- 결과: 전 카테고리 "예상 건수" == "수집됨" 정확히 일치, 총 33,496건 (README 예상치와 동일)
- 캐시된 페이지 702개

### 상세 크롤링 소규모 테스트 (2026-07-30, 같은 세션)
- 사용자가 `--limit 100` 테스트 먼저 진행하기로 선택
- `python scraper.py crawl-details --all --delay 0.8 --limit 100` (백그라운드) → 100/100 성공
- HTML 크기 검증: 45,998~46,868바이트로 일관, 404/에러 페이지 없음 → 정상 판단
- 참고: `__NEXT_DATA__` 마커는 샘플에서 미검출 — 2단계(구조화 파싱) 작업 시 실제 데이터
  임베딩 방식(RSC payload 등)을 다시 확인해야 할 수 있음

### 전체 상세 크롤링 시작 (2026-07-30, 같은 세션)
- `python scraper.py crawl-details --all --delay 0.8` 백그라운드 실행 시작
  (task id: bog6wvusn, 이미 완료된 100건은 자동 스킵, 남은 약 33,396건, 예상 7~10시간)

### NEXT_STEPS.md 검토 및 ERD 참고자료 확인 (2026-07-31)
- 사용자가 작성한 `NEXT_STEPS.md` 검토 — 전체 로드맵(구조화 파싱 → 로컬 LLM Text-to-SQL
  검색 → 마무리) 확인
- 문서에 언급된 "예전에 논의했던 DHO 위키 사이트 ERD 설계"를 메모리/옵시디언에서 검색했으나
  발견하지 못함 → 사용자에게 확인
- 사용자 답변: 참고 ERD 없음, 원본 사이트 구조를 그대로 반영해서 스키마 설계하면 됨
- `NEXT_STEPS.md` L24 문구를 이 결정에 맞게 수정, CHANGELOG.md에 기록
- 프로젝트 메모리 저장: `dho-project-overview`, `schema-design-no-erd-reference`

### 전체 상세 크롤링 완료 (2026-07-31)
- 백그라운드 작업(task id: bog6wvusn) 완료, 실패/재시도 0건
- `status` 최종 확인: 33,496 / 33,496건 전부 상세완료, 캐시된 페이지 34,198개
- 1단계(원본 HTML 캐싱) 완전히 종료. `dho_cache.sqlite3`에 pages/categories/items 전체 확보

### 2단계 착수 — 심각한 인코딩 버그 발견 및 수정 (2026-07-31)
- 카테고리별 샘플 상세 페이지(tarotCard/cannon/recipe/consumable/cityNpc/quest/ship) HTML 구조
  분석을 위해 추출하던 중, 캐싱된 한글 텍스트가 전부 mojibake(깨짐) 상태임을 발견
- 원인: dho-archive.vercel.app 서버가 `Content-Type: text/html`에 charset을 명시하지 않아,
  `requests`가 기본값인 ISO-8859-1로 응답을 디코딩함 (`r.encoding` == ISO-8859-1,
  `r.apparent_encoding`(chardet) == utf-8). `scraper.py`의 `fetch()`가 `resp.text`를 그대로
  사용했기 때문에 캐싱된 34,198개 페이지 전체와, 거기서 파싱한 `items.name`/`categories.label`이
  전부 잘못 디코딩된 상태로 저장되어 있었음
- 복구 가능성 검증: latin-1 재인코딩 → utf-8 디코딩 라운드트립으로 원본 UTF-8 바이트를
  손실 없이 복원 가능함을 확인 (`pages.html` 34,198건 전수 검사, 실패 0건)
- 단, `items.name`/`categories.label`은 파싱 시 `get_text(strip=True)`가 깨진 문자열 위에서
  `.strip()`을 호출하면서 일부 이름의 마지막 글자가 영구 손실됨 (약 1,225개 항목, 4개 카테고리
  라벨 — 예: "이순신"→끝글자 잘림, "침몰선"→"침몰"). `pages.html`은 `.strip()`을 거치지 않아
  이 문제가 없었음
- 조치:
  1. `scraper.py` `fetch()`에 `resp.encoding = "utf-8"` 명시 추가 (향후 크롤링 정상화)
  2. DB 백업 (`dho_cache.sqlite3.bak_before_encoding_fix`, 1.4GB)
  3. `pages.html` 전체를 latin1→utf8 라운드트립으로 in-place 복구 (34,198건, 실패 0)
  4. `discover` + `crawl-lists --all` 재실행 → 복구된 캐시에서 재파싱 (네트워크 요청 없이
     캐시만 사용, 기존 `ON CONFLICT DO UPDATE` 로직으로 자동 갱신)
  5. 검증: 이전에 잘렸던 항목("이순신", "침몰선", "레시피책", "직업", "정기선" 등) 전부
     정상 복구 확인. 남은 141건은 실제로 영문/숫자 이름(예: "Age of Revolution")이라 문제없음
- 결과: `pages.html`, `items.name`, `categories.label` 전부 정상 UTF-8 상태로 복구 완료.
  상세 페이지 재크롤링(네트워크 요청) 불필요했음

### 2단계 구조화 DB 작업 (2026-07-31)
- 사용자와 스키마 전략 논의: 카테고리별 전용 테이블 방식 확정 (EAV 아님)
- `plan.md`/`checklist.md`/`context-notes.md` 작성
- 70개 카테고리 샘플 구조 전수 조사(`all_categories_fields.txt`) → 사이트 전체가
  "속성-값 행 + 표" 일관 구조를 쓰는 것 확인, "획득 방법" 표가 카테고리 무관하게
  같은 헤더 모양을 반복하는 패턴 발견 (cannon 하나에서만 9가지 형태)
- `build_structured_db.py` 작성: 범용 추출기 + 스테이징(items_core/raw_attrs/raw_tables),
  전체 33,496건 처리 완료 (실패 0)
- `build_acquisition.py` 작성: 카테고리 공유 관계 테이블 9종 매핑
  (item_detail_list 99,800행, item_transmutation_* 정책22,409/스킬44,817/재료67,221,
  item_acquisition_seller 13,807, item_acquisition_recipe 계열 등) — 사용자가 직접
  선택한 진행 순서(공유 획득방법 테이블 우선)
- `materialize_cannon.py` 작성: cannon 카테고리 전용 테이블 파일럿, 566건 검증 완료
  (원본 HTML과 스탯 값 대조 일치 확인, transmutation 정책/스킬/재료 3단 분리로
  스킬×재료 교차곱 오류 방지)
- 남은 69개 카테고리는 `checklist.md`/`context-notes.md`에 진행 방법과 함께 기록,
  다음 세션에서 이어서 진행

### 카테고리 3개 추가 진행 (2026-07-31, 사용자 요청 "몇개만 더")
- `item_acquisition_directsale`(판매기간/수량/가격) 공유 테이블 추가 (416행 대상)
- `recipe`: 분류/레시피책 + `recipe_product`(생산품) 테이블. "필요"는 공유 item_detail_list로
  이미 커버됨. 3,045건 전부 적재, 원본 대조 검증(item 9426) 일치
- `consumable`: 분류/사용효과. 획득방법은 판매NPC/레시피/직접판매 전부 공유 테이블로 커버되어
  전용 관계 테이블 불필요. 2,510건 전부 적재, 원본 대조 검증(item 1016552) 일치
- `tarotCard`: 효과/요약. 입수NPC는 공유 item_acquisition_npc_location이 헤더 모양만으로
  자동 매핑 — 전용 코드 작성 없이 커버됨 (공유 테이블 아키텍처 효과 확인). 22건 전부 적재,
  원본 대조 검증(item 8611) 일치
- 4/70 카테고리 완료. checklist.md 최신화

### 나머지 66개 카테고리 자동화로 전체 완료 (2026-07-31, 사용자 요청)
- 수동 방식으로 66개를 전부 하면 25~35시간 예상된다고 안내 → 사용자가 자동화 방식으로
  전환 결정 (품질 85~90%, 시간 10% 트레이드오프 설명 후 동의). "차후 부분적으로 정확도
  개선 가능한지" 확인 요청 → 원본 raw_attrs/raw_tables가 보존되어 있어 가능하다고 답변
- `build_acquisition.py`에 `COVERED_HEADER_SHAPES` 상수 추가 (이미 공유 테이블로 처리된
  표 헤더 모양 목록, materialize_generic.py가 재사용)
- `materialize_generic.py` 작성: 카테고리별 전용 테이블을 자동 생성
  - 속성 라벨을 컬럼명으로 그대로 사용(번역 안 함), 값이 전부 숫자면 INTEGER 자동 판별
  - 링크가 0~1개인 라벨은 `_id`/`_분류` 외래키 컬럼 자동 추가
  - 표는 공유 패턴(COVERED_HEADER_SHAPES)이면 건너뛰고, 아니면 `{카테고리}__{라벨}`
    관계 테이블로 자동 생성 (여러 헤더 모양이 섞이면 합집합으로 컬럼 구성)
- 66개 카테고리 전부 예외 없이 처리 (aide~treasureMap). 대표로 ship(1016347 신형
  서프라이즈), equipment(6582 코모두스 황제의 검), city(11599 리가) 원본과 대조 검증 —
  전부 정확히 일치
- 알려진 한계: 쉼표 포함 숫자("1,183")는 TEXT로 남음, 링크 2개 이상 셀은 첫 번째만
  외래키로 잡힘 — 원본 데이터는 그대로 있어 필요한 카테고리만 나중에 개선 가능
- **결과: 전체 70/70 카테고리 완료.** `dho_structured.sqlite3` 총 211개 테이블

### 3단계 방향 논의 (2026-07-31)
- 사용자 질문에 3단계(로컬 LLM Text-to-SQL) 진행 방식 설명: 질문→SQL생성→실행→결과
  요약 파이프라인, Ollama+Qwen2.5 등 로컬 모델 사용
- 핵심 난관 공유: 테이블이 211개라 전체 스키마를 프롬프트에 넣기엔 로컬 7B/14B 모델
  컨텍스트로 부담됨 → 질문에서 카테고리를 먼저 좁히고 관련 테이블만 프롬프트에 넣는
  2단계 방식 추천 (트레이드오프: 카테고리 판별 오류 시 잘못된 스키마로 SQL 생성 위험)
- 사용자가 다음 세션에 이어가기로 결정, 이번 세션은 여기서 종료

### 미해결
- 스키마 문서화 (Text-to-SQL 프롬프트용 테이블/컬럼 요약) 아직 안 함
- 3단계: 로컬 LLM(Text-to-SQL) 연동 검색 미착수 — 다음 세션에서 카테고리 좁히기 전략부터
  구체화 예정
- 자동화 66개 중 필요한 카테고리만 선별해서 정밀도 개선 가능 (사용자 판단 대기)
- 3단계: 로컬 LLM(Text-to-SQL) 연동 검색 미착수
- `dho_cache.sqlite3.bak_before_encoding_fix` 백업 파일 존재 (1.4GB) — 복구 검증 끝나면
  사용자 판단하에 삭제 가능
- 콘솔 출력 한글 인코딩 깨짐 현상 있음 (기능에는 영향 없음, PowerShell 콘솔 코드페이지 이슈로 추정)
