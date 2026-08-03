# NAS 실배포 및 배포 후 발견된 버그 3건 수정

## 배경
- 직전 세션에서 로컬 Docker 빌드/기동까지 검증하고 NAS(`\\192.168.0.200\docker\dho_chat`,
  Synology `/volume1/docker/dho_chat`)로 파일까지 복사해뒀던 상태
- 사용자가 NAS에서 직접 `docker compose up -d --build chat`를 실행하며 실배포 진행,
  중간중간 발생한 에러를 로그로 공유받아 원격으로 진단/수정

## 1. 첫 배포: 질문만 하면 500 에러
- 사용자가 실제로 챗봇에 질문하면 "서버 에러가 발생하네"라고만 알려줘서, 먼저 LAN으로
  `http://192.168.0.200:3000/api/chat`에 직접 curl로 재현 — "안녕" 같은 도구 호출도
  필요없는 간단한 메시지도 스트리밍 없이 바로 `text/plain 500 Internal Server Error`
  (SSE 에러 형식이 아님 → 스트림 시작 전에 죽는다는 신호)
- 로그 요청해서 확인: `Error [AI_InvalidArgumentError]: baseURL must be a non-empty
  string`가 **module evaluation** 시점에 발생. `createOpenAI()`를 route.ts 최상단에서
  호출하고 있었는데, Docker 빌드 시점엔 `OPENAI_API_BASE_URL` 환경변수가 없어서
  Next.js가 이걸 빈 값으로 빌드 결과물에 인라인해버림 → 컨테이너 실행 시
  docker-compose가 넣어주는 진짜 런타임 값을 영영 못 봄
- 수정: `createOpenAI()` 호출을 POST 핸들러 안(요청 처리 시점)으로 이동
- 검증: 로컬에서 "빌드 타임엔 환경변수 없음, 실행 시점에만 있음"인 정확히 동일한
  시나리오로 재현 → 수정 후 실제 OpenAI API까지 요청 도달(플레이스홀더 키라 401,
  즉 배선 정상) 확인. 수정된 route.ts만 SMB로 NAS에 먼저 복사해둠

## 2. 재배포 방법: 나는 SSH 권한이 없음
- 사용자가 "NAS에서 직접 재빌드+재기동해주세요"라고 했지만, SSH 접속 테스트해보니
  포트는 열려있어도 인증 정보(키/비밀번호)가 없어서 로그인 불가 확인
- 지금까지 했던 건 전부 SMB 파일 공유 접근만으로 가능했던 것이고, 실제 `docker
  compose` 명령 실행은 NAS에 직접 접속하셔야 한다고 명확히 안내

## 3. 재배포 후: "데이터베이스 파일을 열 수 없음"
- route.ts 수정 반영해서 재빌드+재기동 후, 실제 질문("준사관 우대 스킬")에 모델이
  get_item_detail 도구를 호출했는데 DB 연결 실패 → 모델이 이걸 사용자에게 되물어보는
  형태로 우아하게 응답(AI SDK가 도구 실행 에러를 잡아서 모델에게 결과로 넘겨준 것,
  요청 자체는 안 죽음)
- `docker compose logs`에는 이 에러가 안 찍힘(도구 실행 에러는 AI SDK 내부에서
  처리되고 별도 console.error가 없어서) → 대신 컨테이너 안에서 직접
  `ls -la /data/dbsql/dho_structured.sqlite3` + `node:sqlite`로 직접 열어보는 진단
  명령을 만들어서 실행 요청
- 결과: `Permission denied` — Windows SMB로 복사된 `dho_structured.sqlite3`를
  컨테이너의 비루트 사용자(Dockerfile에서 `USER nextjs`, uid 1001)가 읽을 권한이 없는
  상태였음
- 수정: NAS에서 `sudo chmod -R a+rX /volume1/docker/dho_chat` 실행 요청 → 정상 동작
  확인("잘 실행되고 있어")

## 진단 방법론 메모
- 매 단계마다 "무슨 일이 일어났는지"를 추측으로 땜빵하지 않고, 실제 로그/curl 재현/
  컨테이너 내부 직접 진단 명령으로 정확한 원인을 먼저 확보한 뒤 수정함 — 배포 환경에
  SSH 접근이 없는 제약 안에서도 "사용자가 실행하고 결과를 붙여주는" 사이클로 원격
  디버깅 가능했음
- 세 가지 버그 모두 "로컬 테스트로는 안 드러나고 실제 배포 환경에서만 드러나는" 종류
  (빌드타임 vs 런타임 환경변수, OS/파일시스템 간 권한 이관, robocopy 경로 매칭)였다는
  공통점 — 로컬 Docker 테스트를 아무리 꼼꼼히 해도 SMB 복사나 Synology 특유의 권한
  모델까지는 재현이 안 됐음

## 결정
- 향후 `dho_structured.sqlite3`를 재스테이징해서 SMB로 재동기화할 때마다 chmod 재실행이
  필요할 수 있음을 NEXT_STEPS.md/CHANGELOG.md에 명시해둠(자동화는 안 함, 매번 수동)

## 미해결
- 더 다양한 실사용 질문으로 회귀 테스트
- 로컬(Windows) openwebui/ollama 고아 컨테이너 정리 여부
- 모델의 SQL 조인 실패 패턴이 또 나오면 get_item_detail류 헬퍼 추가 검토
