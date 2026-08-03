# OpenWebUI → Vercel AI SDK 직접 구축 프론트로 교체

## 요청
- "지금 openwebui로 되어 있는걸 변경하고 싶어" — 범위가 불명확해서 확인 질문(채팅 UI
  자체 교체 / 모델·API 설정 변경 / 배포·인프라 구성 변경 중 선택)했고, "프론트를 Vercel
  AI SDK를 이용해서 직접 구축해줘"로 확정됨

## 배경
- 지금까지 LLM 검색 기능은 OpenWebUI(오픈소스 채팅 UI) + `openwebui_tool_dho_sql.py`
  (OpenWebUI의 "Tool" 플러그인 형식으로 작성된 Text-to-SQL 함수 6개) 조합으로 구현돼
  있었음 (`docker-compose.yml`로 배포)
- 이번 요청은 OpenWebUI라는 기성 프론트엔드 자체를 걷어내고, Vercel AI SDK로 직접 채팅
  UI를 만들어달라는 것

## 행동
- `chat/` 서브프로젝트 신규 생성: `create-next-app`으로 스캐폴딩(App Router, TypeScript,
  Tailwind), `ai`/`@ai-sdk/openai`/`@ai-sdk/react`/`zod` 설치
- **버전 이슈**: 설치된 Next.js가 16.2.12로 학습 데이터 시점보다 최신이라, 프로젝트에
  자동 배치된 `AGENTS.md`가 "이 버전은 breaking change가 있을 수 있으니
  `node_modules/next/dist/docs`를 먼저 읽으라"고 안내함 → route.js/env 문서를 실제로
  읽고 나서 작업 시작. `ai` 패키지도 v7까지 올라가 있어서(`@ai-sdk/openai`/`@ai-sdk/react`는
  v4) 타입 선언 파일(`node_modules/@ai-sdk/provider-utils/dist/index.d.ts` 등)을 직접
  grep해서 `tool()`이 `inputSchema` 필드를 쓰는지, `useChat`이 `sendMessage({text})`
  방식인지, `streamText().toUIMessageStreamResponse()`가 맞는지 등을 확인하며 코드 작성
  (기억에 의존하지 않고 실제 설치된 버전의 타입 정의를 대조함)
- `chat/lib/dho-db.ts`: `openwebui_tool_dho_sql.py`의 6개 함수(list_categories/
  get_item_detail/search_items/find_tables/get_table_schema/run_sql)를 Node.js 내장
  `node:sqlite`(Node 22.5+ 실험적 API, 현재 Node v24.15.0이라 사용 가능)의 `DatabaseSync`
  로 그대로 포팅. `better-sqlite3` 같은 네이티브 컴파일 필요한 패키지 대신 내장 모듈을
  써서 Windows에서 빌드 이슈 없이 동작
- `chat/app/api/chat/route.ts`: `streamText` + `stopWhen: stepCountIs(8)`로 멀티스텝
  도구 호출(예: list_categories → find_tables → get_table_schema → run_sql 체이닝)
  지원, 시스템 프롬프트는 원래 Python 도구의 모듈 docstring 안내를 그대로 이식.
  `runtime = "nodejs"` 명시(`node:sqlite`가 Edge 런타임에서 안 돌아감)
- `chat/app/page.tsx`: `useChat` + `DefaultChatTransport`로 다크 테마 채팅 UI,
  텍스트/도구 호출 파트를 구분해서 렌더링(도구 호출은 "🔧 도구명(인자) — 상태" 형식으로
  표시)
- **버그**: 처음 작성 시 `convertToModelMessages(messages)`를 동기 함수로 착각하고
  바로 `streamText`의 `messages` 필드에 넣었더니 타입에러(`Promise<ModelMessage[]>`가
  아니라 실제 배열이 필요) — 이 버전에서 `convertToModelMessages`가 비동기로 바뀐 것을
  타입 정의 확인 후 발견, `await` 추가해서 해결
- **버그**: `node:sqlite` 타입을 못 찾는다는 에러 — 설치된 `@types/node`가 20.x라
  Node 22.5+에 추가된 `node:sqlite` 타입이 없었음. `@types/node@24`로 올려서 해결
  (실제 런타임 Node 버전인 v24.15.0과 맞춤)
- 검증: `npx tsc --noEmit`로 타입 체크 통과, `lib/dho-db.ts`의 함수들을 스크립트로 직접
  실행해서 실제 DB 조회 결과 확인(코모두스 황제의 검 검색 등 정상), `npm run dev`로
  개발 서버 기동 후 페이지 스크린샷 확인, `/api/chat`에 curl로 직접 요청 보내서 라우팅이
  실제 모델 호출 직전까지 정상 도달하는지 확인 — API 키가 없어서
  `AI_LoadAPIKeyError`로 막히는 것까지 확인(이건 예상된 결과, 배선 자체는 정상이라는
  뜻). 실제 API 키 없이는 이 이상 검증 불가

## 결정
- 기존 `docker-compose.yml`(openwebui 서비스)과 `openwebui_tool_dho_sql.py`는 삭제하지
  않고 그대로 둠 — 사용자가 이 새 프론트가 잘 동작하는 걸 확인하기 전까지는 롤백 여지를
  남겨두는 게 안전하다고 판단, 제거는 사용자 확인 후 별도로 진행

## 미해결
- `chat/.env.local`에 실제 API 키를 채워야 실사용(실제 LLM 호출) 테스트 가능 — API 키
  없이는 구조적 검증(라우팅/타입/DB 접근)까지만 확인함
- 기존 openwebui docker-compose 스택 제거 여부 결정
- 새 프론트를 NAS/Docker 배포에도 반영할지는 별도 논의 필요
