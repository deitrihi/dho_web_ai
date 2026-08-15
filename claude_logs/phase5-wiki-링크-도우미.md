# Phase 5 — Wiki.js 링크 도우미 `/link/<이름>`

## 요청
- Wiki.js 문서에서 DHO 항목으로 링크를 걸기가 어렵다 — `[팬시]`처럼 이름만 쓰면 정확히
  매핑되는 문서(들)로 연결되는 쉬운 방법이 없냐는 질문.

## 조사
- WebSearch로 Wiki.js 공식 피드백 보드 확인 — "Auto link creation", "Link to title",
  "Autocomplete links / mentions", "Succinct link syntax" 등 동일 요청이 여러 건 있으나
  전부 미해결(오픈 상태). 현재 배포 버전(2.5.314)엔 정식 기능 없음.
- 커스텀 마크다운 문법(`[link:이름]`)은 Wiki.js 마크다운 파서 플러그인 확장이 필요해
  과함 → 표준 마크다운 링크(`[텍스트](/link/이름)`) + 서버 리다이렉트로 우회하기로 사용자와
  합의(AskUserQuestion 2회).

## 행동
- `dho_webapp.py`: `/link/<name>` 라우트 + `get_link_matches()` 추가. `items_core`의
  `COALESCE(name, title)` 정확 매칭 — 1건이면 Wiki.js 문서로 302, 여러/0건이면
  `templates/link_result.html`로 목록/안내 렌더링.
- `.env.example`: `WIKIJS_PUBLIC_URL` 신규 추가(브라우저가 접속할 실제 주소, 기존
  스크립트 전용 `WIKIJS_URL`과 분리 — chat의 `/chat` 상대경로 패턴과 달리 Wiki.js는 별도
  포트라 절대 URL 필수).
- `templates/link_result.html` 신규 — 기존 `index.html`/`category.html` 스타일 재사용.
- `plan.md`/`checklist.md`/`context-notes.md`/`CHANGELOG.md`에 Phase 5로 기록.

## 결정
- 정확 매칭만 지원(부분/유사 검색 안 함) — 원 요청이 "정확히 매핑되는 문서"였음.
- 0건/2건 이상을 같은 템플릿 하나로 처리, 1건일 때만 코드에서 바로 리다이렉트.

## 검증
- 로컬 `dho-webapp`/`dho-postgres`/`dho-wikijs` 컨테이너에 실제 반영 후 3케이스 확인.
  - 유일 매칭: "귀족의 모닥불" → `consumable/2964582`로 302, 대상 페이지 200 확인
  - 복수 매칭: "알렉산드리아" → city/discovery 2건 목록 정상 렌더링
  - 무매칭: 안내 메시지 정상 렌더링
- 테스트 중 bash heredoc으로 한글을 Python에 넘기면 인코딩이 깨지는 문제 재발 —
  Write 도구로 UTF-8 스크립트 파일을 직접 써서 우회(기존 메모리와 동일 증상/해법).

## 미해결
- NAS `.env`에 실제 `WIKIJS_PUBLIC_URL` 값 채워넣기 — 사용자 확인/작업 필요.
- NAS 재배포 후 실제 `guides/` 문서에 `[텍스트](/link/이름)` 링크를 넣어 브라우저 클릭
  테스트.
