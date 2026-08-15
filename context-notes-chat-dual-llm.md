# 컨텍스트 노트: 챗봇 2단계 LLM 역할 분리

## 결정 사항
- 사용자가 처음엔 "역할을 나눠서 2개 API로 쓰고 싶다"고만 해서, 현재 아키텍처에
  이미 존재하는 두 역할(메인 추론 vs 임베딩)을 설명하고 어떻게 나눌지 명확화 질문을
  준비했으나 사용자가 직접 구체적인 분담안(계획=gpt-5-mini, 실행+정리=deepseek)을
  제시해서 그 방향으로 바로 진행.
- 임베딩(semantic_search_items/wiki)은 DeepSeek에 대응 기능이 없어 이번 분리 대상에서
  제외 — 계속 OpenAI(text-embedding-3-small) 사용.
- DeepSeek 연동은 별도 패키지(@ai-sdk/deepseek) 추가 없이 기존 @ai-sdk/openai의
  createOpenAI()를 baseURL만 바꿔 재사용(DeepSeek API가 OpenAI 호환이라 가능). 이미
  프로젝트가 OPENAI_API_BASE_URL을 런타임에 오버라이드하는 패턴을 쓰고 있어서 동일
  관례 유지.
- 계획 단계(gpt-5-mini)는 도구를 아예 바인딩하지 않은 generateText 호출로 만들어서,
  "계획만 세우고 실행은 안 함"을 프롬프트 지시가 아니라 구조적으로 강제.
- 계획 단계 실패 시 폴백 로직은 추가하지 않음 — 기존에도 OpenAI 키/네트워크 오류는
  최상위 try/catch + streamText의 onError가 잡아서 500 + 로그로 처리하던 것과 동일한
  수준으로 유지(요청 범위 밖의 신규 에러 핸들링 추가 지양).

## NAS 배포 후 발견된 버그 2건과 수정

### 1. 연속 질문 시 서버 에러 (`AI_APICallError: Invalid 'input[2].id'`, 400)
- 증상: 실사용 중 챗봇에 두 번째 질문부터 "서버 에러가 발생했습니다" 응답.
- 원인: 1단계(계획, gpt-5-mini)는 OpenAI Responses API(`/v1/responses`)를 쓰는데, 이
  API는 대화 히스토리에 포함된 항목의 ID가 OpenAI 자신이 발급한 형식이어야 함. 그런데
  1단계 호출에 `convertToModelMessages(messages)`로 만든 전체 히스토리를 그대로
  넘기고 있어서, 이전 턴에 2단계(deepseek)가 만든 도구 호출 기록(AI SDK가 임의로 붙인
  UUID 형식 ID)이 그대로 섞여 들어감 -> OpenAI가 "자기 형식이 아닌 ID"라며 400 거부.
  첫 질문은 히스토리에 도구 호출이 없어 통과하고, 두 번째 질문부터 재현됨(사용자 증상과
  정확히 일치).
- 1차 수정(불충분): 1단계로 보내는 메시지에서 `part.type === "text"`만 남기고 도구
  호출/결과 파트를 제거(`convertToModelMessages` 그대로 사용). 재배포 후 재현 테스트에서
  같은 에러(`input[2].id`)가 그대로 재발 — 사용자가 "아직도 에러가 발생했어"로 알려줘서
  재조사.
- 재조사로 밝힌 진짜 원인: `TextUIPart`는 `providerMetadata` 필드를 갖고 있고(AI SDK
  타입 정의 확인), `convertToModelMessages`는 이걸 그대로 `providerOptions`로 옮겨줌.
  2단계(deepseek)가 만든 응답 텍스트에 붙는 providerMetadata는 "openai" 네임스페이스로
  태깅되는데(같은 `@ai-sdk/openai` 패키지를 baseURL만 바꿔 재사용하는 구조라 provider
  이름이 실제 백엔드와 무관하게 "openai"로 고정됨), `@ai-sdk/openai`의 Responses API
  요청 빌더(`convertToOpenAIResponsesInput`, `node_modules/@ai-sdk/openai/dist/index.js`
  약 3957번째 줄 "assistant"/"text" 케이스)가 `part.providerOptions.openai.itemId`를
  "이전에 OpenAI 자신이 발급한 항목 ID"로 해석해서 그대로 요청에 실음 -> 실제로는
  deepseek 쪽 ID라 OpenAI Responses API의 형식 검증에서 거부됨. 텍스트 파트만 필터링해도
  providerMetadata 자체는 안 지워지므로 1차 수정으로는 못 고친 것.
- 최종 수정: `convertToModelMessages`를 아예 쓰지 않고, 1단계 메시지를 UIMessage의
  text 파트에서 문자열만 뽑아 `{role, content}` 형태로 직접 구성(`chat/app/api/chat/
  route.ts`의 `planningMessages`). provider 메타데이터가 애초에 안 실리므로 이 문제가
  구조적으로 재발 불가능.
- 검증: NAS 재배포 후 사용자가 실제 연속 질문으로 재테스트, 정상 응답 확인 완료.

### 2. `/chat/logs`에 에러가 안 쌓임 (`EACCES: permission denied`)
- 증상: 도커 콘솔 로그(`docker compose logs chat`)에는 에러가 찍히는데 `/chat/logs`
  페이지(JSONL 파일 기반)에는 아무것도 안 쌓임.
- 원인: `chat/Dockerfile`이 비root 사용자(`nextjs`, uid 1001)로 프로세스를 돌리는데,
  `chat_logs` named volume 마운트 지점(`/data/logs`)을 이미지에 미리 안 만들어둠 ->
  Docker가 볼륨을 처음 만들 때 root:root 소유로 생성 -> `fs.appendFileSync`가
  `EACCES`로 실패(`fs.mkdirSync`는 디렉터리가 이미 있으면 조용히 통과해서 그 단계는
  에러가 안 남).
- 수정: `USER nextjs` 전에 `mkdir -p /data/logs && chown -R nextjs:nodejs /data/logs`
  추가(새로 만드는 볼륨은 이제부터 정상 권한으로 시작). NAS의 기존
  `dho_dbsql_chat_logs` 볼륨은 이미 root 소유로 생성돼 있어서 이미지만 고쳐선 안
  바뀜 -> `docker exec -u root dho-chat chown -R nextjs:nodejs /data/logs`로 실행 중
  컨테이너에서 직접 소유권 변경.
- 검증: `docker exec dho-chat touch /data/logs/test-write`로 실제 쓰기 성공 확인.

## 역할 재배치 + 실시간 스트리밍 (2026-08-14)
- 사용자가 새로 제안한 역할 분담: "질문 분석/SQL 생성(트리거)은 gpt-5-mini, 위키+DB
  결과를 묶어 길고 가성비 있는 최종 답변을 쓰는 건 deepseek". 기존(계획=gpt-5-mini,
  실행+답변=deepseek)과 정반대 — gpt-5-mini가 실제 도구 실행을 전담하고 deepseek는
  도구 없이 정리만 함.
- 비용 관점 확인: 출력 토큰 대부분을 차지하는 건 "긴 최종 답변"이지 도구 호출 JSON이
  아니므로, 비싼 모델(gpt-5-mini)이 짧은 도구 호출만 담당하고 싼 모델(deepseek)이 긴
  텍스트 생성을 담당하는 게 총 비용 면에서 유리 — 사용자 판단이 합리적이라고 판단하고
  그대로 채택.
- 구현: `EXECUTION_SYSTEM_PROMPT`(gpt-5-mini, 도구 9개 바인딩, 마지막에 답변 대신
  "자료 수집을 마쳤습니다" 같은 짧은 문구만 남기도록 지시) + `SYNTHESIS_SYSTEM_PROMPT`
  (deepseek, 도구 없음, 원본 실행 프롬프트에 있던 자료 해석 규칙 — qty 정렬,
  similarity 필터링, wiki grounded_item 우선순위 — 을 그대로 옮겨옴. deepseek는
  도구를 직접 호출한 적이 없으므로 이 판단 규칙을 몰라서 명시가 필요했음).
- `execution.toolResults`(AI SDK `StreamTextResult.toolResults: PromiseLike<...>`)로
  1단계의 전체 도구 호출 결과를 모아 `formatGatheredData()`로 직렬화해서 2단계 system
  프롬프트에 첨부.
- 이어서 사용자가 "질문 직후부터 아무 응답도 없는 게 답답하다"고 지적 — 두 단계를
  순차 대기(await 후 응답)하면 1단계가 끝날 때까지 화면이 비어있는 문제는 여전했음.
  `createUIMessageStream({execute: async ({writer}) => {...}})` +
  `writer.merge(toUIMessageStream({stream: result.fullStream, ...}))` 패턴으로 두
  streamText 호출을 하나의 응답 스트림에 이어붙임 — 1단계는 `sendFinish:false`(메시지를
  안 끝냄), 2단계는 `sendStart:false`(새 메시지를 시작 안 하고 이어붙임)로 설정해서
  하나의 assistant 메시지 안에 "도구 호출 카드들 -> 최종 답변 텍스트"가 실시간으로
  순서대로 쌓이게 함. 프론트(`page.tsx`)는 이미 tool/text 파트를 범용으로 렌더링하고
  있어서 별도 수정 불필요.
- 전환기 트레이드오프(의도적으로 손 안 댐): 이제부터는 도구 호출을 gpt-5-mini만
  전담하므로 그 자체 히스토리는 항상 OpenAI 자기 형식 ID라 위 "input[2].id" 버그
  클래스가 구조적으로 재발 불가능해짐. 다만 이 배포 직전까지 deepseek가 만들어둔
  구버전 히스토리가 남아있는 브라우저 탭이 있다면(새로고침 안 한 경우) 같은 문제가
  한 번 더 뜰 수 있음 — 서버에 대화가 영속 저장되지 않는 구조(useChat 기본, 새로고침시
  히스토리 소실)라 자연스럽게 해소되는 좁은 범위의 문제라 별도 방어 코드는 추가 안 함.

## 미해결/확인 필요
- `deepseek-v4-flash`라는 모델 ID가 실제 DeepSeek API에 존재하는지는 이 세션에서
  명시적으로 검증하지 않음(사용자가 지정한 이름을 그대로 env 기본값으로 사용) — 다만
  실사용 스크린샷에서 `get_item_detail` 도구 호출과 정상 답변 생성이 확인돼(변성연금
  대포 질문 응답) 실제로는 정상 통신되고 있는 것으로 보임.
- 연속 질문 버그: 사용자가 재테스트해서 정상 동작 확인함(2026-08-12).
