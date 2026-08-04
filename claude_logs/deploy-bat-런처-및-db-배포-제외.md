# deploy.bat 런처 추가 및 DB 배포 제외

## 요청 1 — sqlite 파일 배포 제외
- "sqlite 파일은 서버에 있는게 더 최신일꺼 같으니, 배포에서 제외해줘" — webapp의 항목
  추가/수정 기능이 서버 DB에 직접 쓰기 때문에 배포할 때마다 로컬(구버전)로 덮어써버리면
  안 됨.

## 행동 1
- `deploy.sh`의 `EXCLUDE_PATTERNS`에 `dho_structured.sqlite3` 추가.
- rsync는 `--exclude`된 파일을 비교 대상에서 아예 빼서 `--delete`로도 안 지우고, tar는
  아카이브에 없는 파일이라 추출 시 서버 파일이 그대로 유지됨 — rsync-daemon/rsync-ssh/tar
  세 가지 전송 모드 모두에서 안전하게 보호됨.
- 관련 안내 문구("2/4 코드 + DB 전송" → "코드 전송", tar 모드 안내에서 "DB 때문에 시간이
  걸릴 수 있음" 문구 제거)와 상단 주석도 함께 정리.

## 요청 2 — 실행 편의성 (deploy.bat)
- "`& \"C:\Program Files\Git\bin\bash.exe\" ./deploy.sh` 라고 입력하는 것 자체가 너무
  어려운데, batch 파일이라도 만들어줘"

## 행동 2
- `deploy.bat` 신규 생성 — Git Bash 경로 존재 확인 후 `./deploy.sh`에 인자(webapp/chat)
  그대로 전달, Git Bash 없으면 안내 후 종료, 끝나면 키 입력 대기(더블클릭 실행 시에도
  결과를 보고 닫을 수 있게).

## 발견한 문제 — cmd.exe의 UTF-8 batch 파싱 버그
- 한글 주석/echo 문구를 넣은 첫 버전을 `cmd /c deploy.bat webapp`으로 실제 테스트하니
  `'etlocal' is not recognized` 같은 식으로 REM/echo 줄의 한글 뒤쪽 바이트가 다음 줄
  앞부분까지 갉아먹는 형태로 매번 다르게 깨짐.
- UTF-8 BOM 추가, 파일 맨 위에 `chcp 65001 >nul` 삽입 둘 다 시도했지만 동일하게 재현됨 —
  파일 자체는 유효한 UTF-8(BOM 포함, `xxd`로 바이트 확인)이라 파일 손상이 아니라 cmd.exe
  자체의 멀티바이트 batch 파싱 문제로 판단.
- 해결: `deploy.bat` 본문을 전부 ASCII(영어)로 재작성. 한글 안내문은 `deploy.sh`가 Git
  Bash 안에서 출력하는 부분(정상 동작 확인됨)에서만 나오고, `deploy.bat`은 얇은 런처
  역할만 하므로 영어로 바꿔도 기능상 문제 없음.

## 검증
- `echo "" | cmd /c "deploy.bat" webapp` — 인코딩 수정 전: 매 실행마다 다른 지점에서
  `is not recognized as an internal or external command` 오류로 실패.
- 수정 후: 전송(tar, DB 제외 확인) → NAS 원격 빌드 → 컨테이너 기동까지 정상 완료,
  `docker compose ps`로 `Running` 확인.

## 결정
- `deploy.bat`은 CLAUDE.md의 "신규 파일 한글 헤더 주석" 관례에서 예외 처리 — cmd.exe의
  UTF-8 batch 파싱 버그가 실행 실패로 직결되는 기술적 제약이라 영어로 유지.

## 미해결
- 없음
