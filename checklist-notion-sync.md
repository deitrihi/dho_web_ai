# 노션 데이터 챗봇 검색 연동 체크리스트

## 조사
- [x] 기존 파이프라인 스크립트 패턴 확인 (`build_search_index.py`, `materialize_*.py`)
- [x] `chat/lib/dho-db.ts` / `chat/app/api/chat/route.ts` 도구 등록 패턴 확인
- [x] `.env`/`NOTION_API_KEY` 존재 확인, `requests` 사용 가능 확인 (notion-client 미설치 —
      requests로 직접 REST 호출하기로 결정)
- [x] `.gitignore`에 `dho_structured.sqlite3`/`.env` 포함 확인 (개인 노션 데이터 커밋 위험 없음)

## 스키마 + 동기화 스크립트
- [x] `sync_notion.py` 작성 — 상위 페이지 재귀 수집 + `notion_pages`/`notion_fts` 적재
- [x] 실제 사용자 페이지로 1회 실행해서 정상 적재 확인 (로컬, 50개 페이지)
- [x] `notion_fts` MATCH 쿼리로 샘플 검색 검증 (3글자 이상 키워드로 정상 매칭 확인)

## 챗봇 연동
- [x] `chat/lib/dho-db.ts`에 `searchNotion()` 추가
- [x] `chat/app/api/chat/route.ts`에 `search_notion` 도구 등록 + SYSTEM_PROMPT 보강
- [x] `npx tsc --noEmit` 타입체크 통과 확인
- [ ] 챗봇 개발 서버(또는 NAS 배포본)에서 실제 질문으로 동작 확인 (사용자 배포 후)

## 스케줄링 — NAS가 주 사용처로 확인되어 방향 변경 (Windows 스케줄러 → 컨테이너 루프)
- [x] `Dockerfile.notion-sync` + `sync_notion_loop.sh` 작성 (하루 1회 반복)
- [x] `docker-compose.yml`에 `notion-sync` 서비스 추가 (webapp과 동일하게 DB 읽기-쓰기 마운트)
- [x] `deploy.sh`에 `notion-sync` 서비스 인자 추가
- [x] `.env`/`.env.example`에 `NOTION_ROOT_PAGE` 추가
- [x] `docker compose config`로 YAML 유효성 검증
- [ ] `docker compose build notion-sync` 실제 빌드 검증 — 로컬 Docker 데몬 미실행으로
      확인 못 함, NAS 배포 시(`./deploy.sh` 4/4 단계) 확인 필요
- [ ] 사용자가 `./deploy.sh` 또는 `./deploy.sh notion-sync` 실행해서 NAS에 반영

## 문서화
- [x] README에 노션 동기화 섹션 추가 (로컬/NAS 두 경로 모두)
- [x] CHANGELOG.md `[미커밋]`에 기록
- [x] claude_logs 세션 로그 기록

## 부수 발견 수정 — webapp Dockerfile의 build_search_index.py 누락
- [x] `Dockerfile`의 `COPY` 목록에 `build_search_index.py` 추가
- [x] `DERIVED_PIPELINE_SCRIPTS`(8개) 전체와 `COPY` 목록 대조해서 다른 누락 없음 확인
- [x] `build_search_index.py`가 stdlib만 씀(추가 pip 의존성 없음) 확인 —
      `requirements.txt` 변경 불필요
