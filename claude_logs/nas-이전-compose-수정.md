# NAS 이전 — docker-compose 수정

## 요청
- 로컬 PC에 구축된 docker 스택(ollama+openwebui)을 NAS로 옮기려 함.
- ollama는 GPU가 안 돌아서 로컬 PC(RTX 3060)로 뺐던 것 — AI API를 쓸 경우 NAS로 가도 괜찮은지 확인.
- 확인 후 compose 파일 수정 요청.

## 행동
- `docker-compose.yml` 수정: GPU 예약이 필요한 `ollama` 서비스와 `ollama` named volume 제거.
  `openwebui` 서비스에 `OPENAI_API_BASE_URL`/`OPENAI_API_KEY` 환경변수 추가(.env에서 로드),
  `ENABLE_OLLAMA_API=false` 추가.
- `.env.example` 신규 생성 (API 엔드포인트/키 템플릿).
- `.gitignore` 신규 생성 (`.env` 제외).
- `CHANGELOG.md` [미커밋]에 위 변경 반영.

## 결정
- NAS(Synology/QNAP 대부분)는 nvidia-container-toolkit 미지원 → ollama 서비스는 API 전환 시
  완전히 제거하는 쪽으로 결정 (조건부 유지 아님).
- API 키는 compose에 평문 노출하지 않고 `.env` + `env_file`로 분리.

## 추가 — API 모델 확정 (gpt-5-mini)
- 사용자가 API 모델을 `gpt-5-mini`(OpenAI)로 확정.
- `docker-compose.yml`에 `DEFAULT_MODELS=${OPENWEBUI_DEFAULT_MODEL}` 추가, `.env.example`의
  `OPENWEBUI_DEFAULT_MODEL`을 `gpt-5-mini`로 지정 (OpenAI 엔드포인트라 base URL은 그대로 유지).

## 미해결 / 후속 확인 필요
- 실제 API 키 값은 사용자가 `.env`에 직접 채워야 함 (템플릿만 제공).
- gpt-5-mini가 `openwebui_tool_dho_sql.py`의 tools(function calling) 호출을 실제로 잘 수행하는지
  실사용 테스트 필요 (기존 로컬 qwen2.5:7b 때처럼 다단계 체이닝 이슈가 있을 수 있음).
- `./:/data/dbsql:ro` 바인드 마운트는 호스트 경로 의존 — NAS로 옮길 때 프로젝트 폴더 자체를
  NAS 경로로 이동해야 함 (별도 확인 필요).
- `openwebui_tool_dho_sql.py` Tool을 계속 쓰려면 선택하는 API 모델이 tools(function calling)
  capability를 지원해야 함 (기존 로컬 qwen2.5:7b와 동일 조건).
- `NEXT_STEPS.md`의 "다음 단계 2"(로컬 LLM/Ollama 전제 서술)를 API 기반으로 수정할지 여부 미정.
