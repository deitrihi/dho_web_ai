# 체크리스트: 챗봇 2단계 LLM 역할 분리

- [x] plan.md / checklist.md / context-notes.md 작성
- [x] `chat/app/api/chat/route.ts` — PLANNING_SYSTEM_PROMPT 추가, deepseek provider 추가,
      generateText로 1단계(계획) 호출, streamText 모델을 deepseek로 교체하고 system에
      계획 텍스트 주입
- [x] `.env.example` — DEEPSEEK_API_BASE_URL/DEEPSEEK_API_KEY/DEEPSEEK_MODEL 추가, 관련
      주석 갱신
- [x] `docker-compose.yml` — chat 서비스 environment에 DEEPSEEK_* 3종 추가
- [x] `npm run build` / `npm run lint` (chat/) 통과 확인
- [x] CHANGELOG.md [미커밋]에 항목 추가
- [x] NAS 배포(`./deploy.sh chat`) 및 실사용 검증
- [x] 연속 질문 시 `AI_APICallError: Invalid 'input[2].id'` 400 에러 발견 → 1차 수정(텍스트
      파트만 필터링)은 재배포 후 재현되어 불충분 확인 → 재조사로 진짜 원인 규명
      (providerMetadata에 deepseek 응답의 "openai" 네임스페이스 itemId가 남아 실제 OpenAI
      Responses API 호출에 그대로 전달됨) → `convertToModelMessages` 대신 순수
      `{role, content}` 문자열로 1단계 메시지 직접 구성 → 재배포 → 사용자 재테스트로
      정상 동작 확인
- [x] `/chat/logs`에 에러가 안 쌓이는 문제 발견(`EACCES`, chat_logs 볼륨 root 소유) →
      `chat/Dockerfile`에서 볼륨 마운트 지점 소유권 사전 설정 → 재배포 → NAS의 기존 볼륨은
      `docker exec -u root`로 직접 chown → 쓰기 테스트로 해소 확인
- [x] 역할 재배치: gpt-5-mini=도구 실행(자료 수집), deepseek=도구 없이 최종 답변 작성
      (비용 최적화: 비싼 모델은 짧은 도구 호출만, 싼 모델이 긴 답변 텍스트 담당)
- [x] "질문 직후 응답 없음" 문제 해결: `createUIMessageStream` + `writer.merge()`로 1단계
      도구 호출을 실시간 스트리밍(`sendFinish:false`) 후 2단계 답변을 같은 메시지에 이어
      스트리밍(`sendStart:false`)
- [x] `npm run build`/`npm run lint` 통과 확인, NAS 재배포 완료
- [ ] 사용자 실사용 검증 대기
