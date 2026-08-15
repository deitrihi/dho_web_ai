# 모바일 반응형 컨텍스트 노트

## 이전 세션 플랜 파일 관계
2단계(구조화 DB) 작업 때 쓰던 `plan.md`/`checklist.md`/`context-notes.md`는
`plan-stage2-structured-db.md` 등으로 이름을 바꿔 보존함(해당 작업 자체는 거의 끝났지만
"다음 세션" 항목이 일부 남아있어 삭제하지 않음). 이번 파일들은 모바일 반응형 작업 전용.

## 근본 원인 진단
`templates/base.html`에 viewport meta 태그가 아예 없었음. 이미 `static/style.css`에
`@media (max-width: 768px)` 규칙이 있었는데도 전혀 효과가 없었던 이유가 이것 — 모바일
브라우저는 viewport meta가 없으면 데스크톱 폭(약 980px 기준)으로 페이지를 렌더링한 뒤
축소해서 보여주므로 미디어 쿼리 자체가 발동하지 않음. "완전히 대응 안 됨"이라는 사용자
표현과 정확히 일치.

chat(Next.js App Router, v16.2.12)은 `generateViewport`/`viewport` export 없이도
Next가 기본 viewport meta(`width=device-width, initial-scale=1`)를 자동 삽입한다는 것을
`node_modules/next/dist/docs/01-app/03-api-reference/04-functions/generate-viewport.md`에서
확인함 — `chat/AGENTS.md`가 "이 버전은 학습 데이터와 다를 수 있으니 문서를 먼저 읽어라"라고
명시해서 실제 문서로 확인 후 진행.

## 설계 결정
- webapp 사이드바를 좁은 화면에서 완전히 숨기기만 하던 기존 규칙은 유지하되(공간 확보),
  대신 topbar에 햄버거 버튼을 추가해 클릭 시 사이드바를 `position: fixed` 드로어로 슬라이드인
  + 백드롭으로 덮는 방식 선택. 별도 JS 프레임워크 없이 순정 JS로 클래스 토글만 처리
  (이 프로젝트는 서버 렌더 MPA라 페이지 이동 시 자연히 닫힘, 별도 상태 관리 불필요).
- chat 쪽 `min-h-screen`(100vh) → `min-h-dvh` 교체는 iOS Safari 등에서 주소창/키보드가
  뷰포트 높이를 동적으로 바꿀 때 하단 입력창이 화면 밖으로 밀리는 문제를 막기 위함
  (Tailwind v4 사용 중이라 `dvh` 유틸 기본 지원 확인).
- 데스크톱 레이아웃/디자인은 최대한 그대로 두고 `@media (max-width: 768px)` 안에서만
  값을 오버라이드하는 방식 유지 (기존 코드 관례를 따름 — 이미 `.shell`에 같은 패턴 존재).
