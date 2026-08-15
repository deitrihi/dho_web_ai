# 챗봇 2단계 LLM 역할 분리 (계획: gpt-5-mini / 실행+정리: deepseek-v4-flash)

## 배경
지금 `chat/app/api/chat/route.ts`는 OpenAI 모델(gpt-5-mini) 하나가 도구 선택 -> SQL
생성 -> 결과 종합 -> 최종 답변까지 전부 담당하는 단일 에이전틱 루프. 사용자 요청:
OpenAI API를 역할별로 나눠서 2개 API(OpenAI gpt-5-mini + DeepSeek deepseek-v4-flash)로
쓰고 싶다. 검색 "계획"은 gpt-5-mini가 세우고, 실제 도구 호출(검색 수행) + 결과 정리
(최종 답변 생성)는 deepseek-v4-flash가 담당하는 2단계 구조로 합의.

## 접근 방식
- **1단계 (계획, gpt-5-mini)**: 도구를 바인딩하지 않은 `generateText` 호출. 시스템
  프롬프트(`PLANNING_SYSTEM_PROMPT`)에 9개 도구의 이름/용도/호출 순서 규칙(기존
  SYSTEM_PROMPT의 노하우 요약)을 담아, 이번 질문에 대해 "어떤 도구를 어떤 순서/키워드로
  호출할지" 5~10줄 텍스트 계획만 생성. 도구가 없으니 실제 호출은 불가능 -> 계획 전용
  역할이 구조적으로 보장됨.
- **2단계 (실행+정리, deepseek-v4-flash)**: 기존 `streamText` + 9개 도구 바인딩 그대로
  유지. system 프롬프트는 기존 SYSTEM_PROMPT + "1단계에서 만든 계획" 텍스트를 덧붙여서
  전달. 실제 Postgres 조회, 결과 종합, 최종 한국어 답변 스트리밍까지 전부 여기서 수행.
- 임베딩(시맨틱 검색, `text-embedding-3-small`)은 DeepSeek에 대응 API가 없으므로 그대로
  OpenAI 유지 — 이번 역할 분리와 무관.
- DeepSeek API는 OpenAI 호환(`https://api.deepseek.com`)이라 새 패키지 없이 기존
  `@ai-sdk/openai`의 `createOpenAI()`를 baseURL만 바꿔 재사용(1단계 openai 인스턴스와는
  별개 인스턴스).
- 신규 env: `DEEPSEEK_API_BASE_URL`(기본 `https://api.deepseek.com`), `DEEPSEEK_API_KEY`,
  `DEEPSEEK_MODEL`(기본 `deepseek-v4-flash`). 기존 `OPENAI_MODEL`은 이제 "계획 모델"
  역할로 의미가 바뀜(주석으로 명시).

## 범위 밖
- 임베딩 모델 교체 없음(계속 OpenAI).
- 계획 단계 실패 시 실행 단계로 폴백하는 별도 로직 추가 안 함 — 기존처럼 최상위
  try/catch(POST 핸들러)가 에러를 잡아 500 응답 + 로그로 처리.
