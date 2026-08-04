# webapp-chat 데이터 동기화 (파생 테이블 자동 재생성)

## 배경
- 이전 세션에서 chat의 `get_backlinks` 수량(qty) 문제를 다루다가, 사용자가 "필요 스킬
  랭크도 못 담는다"며 더 근본적인 "DB Table 고도화" 필요성을 제기.
- 그 논의 중 사용자가 "최종적으로는 webapp과 chat이 동일한 데이터를 봐야 한다(webapp에서
  추가/수정해도 chat 검색·응답에 그대로 반영돼야)"는 핵심 요구사항을 명시.

## 조사
- `dho_webapp.py`의 항목 생성/수정 라우트(`_save_item`)가 실제로 어떤 테이블에 쓰는지
  코드로 확인 — `items_core`/`raw_attrs`/`raw_tables` 딱 세 개뿐. `item_backlinks`,
  `item_acquisition_*`/`item_transmutation_*`/`item_detail_list`, 카테고리 전용 테이블
  (211개)은 전부 오프라인 배치 스크립트(`build_backlinks.py`/`build_acquisition.py`/
  `materialize_*.py`)가 raw 데이터를 읽어 한 번에 만드는 파생 데이터라, webapp이 써도
  자동 갱신 안 됨.
- 결론: 이 문제는 가정이 아니라 **지금 이미 존재하는 상태** — webapp으로 추가한 항목은
  chat의 `get_item_detail`(카테고리 전용 테이블 조회)이나 `get_backlinks`
  (item_backlinks 조회)에 안 잡힘.

## 사용자 확인
- 파생 테이블을 언제 다시 만들지: "저장 즉시 동기 재생성"(추천안) vs "저장은 즉시, 재생성은
  백그라운드" 중 전자 선택.

## 사전 검증 (구현 전)
- 동기 방식이 실제로 감당 가능한지 확인하려고, 7개 파생 스크립트를 실제 DB(백업 후)에
  대고 직접 실행해서 시간 측정 — 총 12초(build_backlinks 4s, build_acquisition 2s,
  materialize_generic 5s, cannon/recipe/consumable/tarotcard 각 0~1s). 결과 행 수가
  기존 CHANGELOG 기록(item_backlinks 440,926 / item_detail_list 99,800 /
  item_acquisition_seller 13,807 등)과 정확히 일치해서 재실행이 안전(멱등)함을 재확인.
  검증 후 백업 파일 삭제.

## 행동
1. **DB 경로 환경변수화**: `build_backlinks.py`/`build_acquisition.py`/
   `materialize_generic.py`/`materialize_cannon.py`/`materialize_recipe.py`/
   `materialize_consumable.py`/`materialize_tarotcard.py` 7개 전부 `STRUCT_DB`를
   하드코딩된 `Path(__file__).parent / "dho_structured.sqlite3"`에서
   `DHO_DB_PATH` 환경변수로 오버라이드 가능하게 변경(webapp/chat과 동일한 관례).
2. **`dho_webapp.py`**: `DERIVED_PIPELINE_SCRIPTS`(7개, 순서: backlinks -> acquisition
   -> generic/cannon/recipe/consumable/tarotcard) + `rebuild_derived_tables()` 추가 —
   각 스크립트를 `subprocess.run([sys.executable, script], env={..., DHO_DB_PATH:
   자신의 DB_PATH})`로 순서대로 실행, 실패해도 저장 자체는 롤백 안 하고 에러만 모아서
   로그로 남김. `item_new`/`item_edit` POST 핸들러에서 `_save_item()` 직후(커밋 완료
   후) 호출.
3. **Dockerfile**: 7개 파생 스크립트를 추가로 `COPY` — 기존엔 `dho_webapp.py`/
   `templates/`/`static/`만 담겨 있어서 이 스크립트들 자체가 webapp 컨테이너 안에
   없었음(로컬에서만 동작하고 NAS 배포본에서는 저장할 때마다 무동작 실패했을 버그,
   이번에 같이 발견해서 수정).
4. **subprocess 인코딩 버그 발견 및 수정**: 첫 end-to-end 테스트에서 자식 스크립트의
   한글 `print()` 출력을 부모가 읽는 백그라운드 스레드마다 `UnicodeDecodeError`가
   대량 발생(자식 프로세스의 stdout 인코딩이 플랫폼/콘솔 코드페이지에 따라 달라지는데
   부모는 UTF-8로 가정하고 디코드). `env["PYTHONUTF8"] = "1"`(자식 강제 UTF-8) +
   `subprocess.run(..., encoding="utf-8")`(부모도 명시적으로 UTF-8 고정)으로 해결.

## 검증
- Flask `test_client`로 실제 `POST /privateFarm/new` 실행 → 응답이 같은 요청 안에서
  `rebuild_derived_tables()`까지 마치고 리다이렉트됨 확인. 저장 전/후 `privateFarm`
  카테고리 전용 테이블 행 수 5 -> 6으로 즉시 반영되는 것 확인(=materialize_generic.py가
  새 항목을 실제로 반영했다는 뜻). 테스트 항목을 items_core/raw_attrs/raw_tables에서
  삭제 후 다시 `rebuild_derived_tables()` 호출로 5로 원복 확인(정리 완료).
- 인코딩 수정 후 재실행 — `UnicodeDecodeError` traceback 전부 사라지고 깨끗하게 통과.
- 기존 라우트 회귀 확인: `/`, `/cannon`, `/cannon/new`, `/assistant` 200(`/cannon/2`는
  단순히 그 item_id가 없어서 404 — 회귀 아님).

## 부수 발견 (이번엔 안 고침, 기록만)
- `tarotCard` 카테고리는 실제 테이블명이 `tarot_card`(스네이크 케이스)라 카테고리
  슬러그(`tarotCard`)와 다름 — chat의 `get_item_detail`이 `SELECT * FROM "${category}"`
  로 조회하므로 tarotCard 항목은 카테고리 전용 상세 정보를 절대 못 찾는 상태(사전 확인용
  테스트 도중 발견, 이번 작업 범위 밖이라 그대로 둠). 나중에 chat 쪽에서 카테고리→실제
  테이블명 매핑을 두거나, materialize_tarotcard.py의 테이블명을 `tarotCard`로 맞추는
  방향으로 고칠 수 있음.

## 미해결
- `item_detail_list`의 수량(qty) 손실 자체(지난 세션 이슈)는 아직 파이프라인 레벨에서
  안 고쳤음 — 이번 작업으로 "webapp 편집이 chat에 반영되는 것"은 해결됐지만, "필요 스킬
  랭크/보상 수량이 애초에 구조화 데이터에 없는" 문제는 별개로 남아있음. 다음 세션에서
  `build_acquisition.py`의 `split_multi_links()`를 고쳐서 `item_detail_list`에 정식
  `qty` 컬럼을 추가하는 근본 수정을 이어서 진행하는 게 좋겠음(이번에 만든
  `rebuild_derived_tables()` 덕분에 이제 이 수정도 webapp 저장 경로에 자동으로 반영됨).
- `tarot_card`/`tarotCard` 테이블명 불일치(위 참고).
