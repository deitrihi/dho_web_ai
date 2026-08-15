# webapp 검색 기능 추가 및 NAS 배포

## 요청
- "webapp에 검색 기능이 필요할 것 같아. LIKE 검색이면 될거 같고, 결과는 카테고리별로
  정리해줘" → 이어서 "nas에 배포 해줘".

## 행동
- `plan-webapp-search.md`/`checklist-webapp-search.md`/`context-notes-webapp-search.md`
  신규 작성.
- `dho_webapp.py`에 `get_search_results()` + `/search?q=` 라우트 추가 — 챗봇용으로 이미
  구축돼 있던 `items_search`(pg_trgm) 테이블을 `ILIKE`로 조회, 카테고리별 COUNT →
  카테고리당 상위 30건 + "외 N건 더"로 그룹핑(`get_backlinks()`와 동일 패턴).
- `templates/search.html` 신규, `templates/base.html` 상단바에 검색창(GET 폼) 추가,
  `static/style.css`에 검색창 스타일 추가(기존 backlink-list/badge 클래스 재사용).
- 로컬 postgres 컨테이너 대상 Flask test_client 스모크 테스트 통과, 로컬 `dho-webapp`
  컨테이너 재빌드/재기동 후 `localhost:5050/search?q=대포`로 24개 카테고리 그룹핑 확인.
- `./deploy.sh webapp`로 NAS(`192.168.0.200:/volume1/docker/dho_dbsql`) 배포 —
  로컬 빌드 검증 → tar 전송 → NAS에서 `docker compose up -d --build webapp`.
  배포 후 `http://192.168.0.200:5050/search?q=대포` 응답이 로컬과 동일(42,178바이트,
  24개 카테고리)한 것으로 정상 반영 확인.
- `CHANGELOG.md` `[미커밋]`에 기록.

## 결정
- 새 검색 인덱스/스키마를 만들지 않고 `build_search_index.py`가 이미 만들어 둔
  `items_search`를 재사용 — webapp과 챗봇 검색 결과가 일관되고, 파생 테이블
  재생성 파이프라인에 스크립트를 더 안 늘려도 됨.
- 그룹핑/카테고리당 상위 N건 표시는 기존 `get_backlinks()` UI 패턴을 그대로 재사용.

## 해결된 문제
- 없음 (신규 기능 추가, 회귀 없이 완료).

## 미해결
- 없음. `dho-webapp` NAS 서비스가 새 검색 기능으로 정상 재기동/응답 확인 완료.
