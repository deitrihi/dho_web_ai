# NAS 배포 스크립트 — SSH 키 인증 전환

## 요청
- "docker compose build가 deploy에서 처리 안 돼서 따로 ssh 접속까지 해서 하고 있는데,
  스크립트 실행 한 번에 docker build까지 되게 해줘"
- 비밀번호를 매번 여러 번 입력해야 하는 것도 같이 불편하다는 맥락

## 원인 진단
- `deploy.sh`는 이미 4/4 단계에서 `sudo docker compose up -d --build`를 원격 실행하도록
  돼 있었지만(직전 세션에서 추가, 미커밋 상태), 두 가지 문제가 겹쳐 사실상 항상 실패해서
  사용자가 매번 직접 SSH로 들어가 build했던 것.
  1. 이 환경(Windows/Git Bash)에 `sshpass`가 없어서, 비밀번호 인증을 쓰는 SSH 호출마다
     (mkdir/.env 확인/build 등 3곳) ssh가 인터랙티브로 비밀번호를 물어봄.
  2. 원격 `sudo docker compose ...`가 pty 없는 비대화형 세션에서 실행돼 sudo가 비밀번호를
     받을 터미널을 못 잡고 "a terminal is required to read the password"로 조용히 실패.

## 행동
- 사용자에게 두 가지 방식 제시 → **A: SSH 키 인증 + docker 그룹 추가(권장)** 선택.
- 새 전용 키페어 생성: `~/.ssh/id_ed25519_nas` (패스프레이즈 없음, 배포 자동화 전용).
- 사용자가 1회 수동 실행(비밀번호 입력이 필요해 도구로는 불가):
  - 공개키를 NAS `deitrihi@192.168.0.200`의 `~/.ssh/authorized_keys`에 등록
  - `sudo usermod -aG docker deitrihi` — 첫 시도는 `cat pubkey | ssh ...` 파이프에 stdin이
    이미 소모돼 sudo가 pty를 못 잡아 실패, `ssh -t`로 pty를 강제해 재시도 후 성공
- `deploy.sh` 수정: `SSH_OPTS`에 `-o BatchMode=yes`(+ 설정 시 `-i "$DEPLOY_KEY"`) 추가,
  sshpass 분기 전체 제거, 4/4 단계의 `sudo` 제거. rsync 데몬 비밀번호(`DEPLOY_RSYNC_PASSWORD`)
  는 SSH 인증과 무관한 별도 체계라 필수값으로 명시(기존엔 `DEPLOY_PASSWORD` fallback이었음).
- `deploy.config.example` 수정: `DEPLOY_PASSWORD` 항목을 `DEPLOY_KEY`로 교체하고, 최초
  1회 설정 커맨드(공개키 등록 + docker 그룹 추가)를 주석으로 남김.
- `deploy.config`(로컬, git 미포함) 수정: 평문 `DEPLOY_PASSWORD` 제거, `DEPLOY_KEY` 설정,
  `DEPLOY_RSYNC_PASSWORD`에 기존 rsync 데몬 비밀번호 이동.
- `CHANGELOG.md` [미커밋]에 항목 추가.

## 검증
- 새 SSH 세션에서 `id` 출력으로 `docker` 그룹(gid 121) 포함 확인, `sudo` 없이
  `docker ps` 성공.
- `./deploy.sh` 실행(webapp+chat 전체) — 비밀번호 프롬프트 0회로 코드+DB 전송(tar) →
  NAS에서 webapp/chat 이미지 원격 빌드 → 컨테이너 재기동까지 한 번에 완료.
  `docker compose ps`로 `dho-webapp`/`dho-chat` 둘 다 `Up` 상태 확인.

## 결정
- 비밀번호 인증(평문 저장 포함)은 완전히 폐기, SSH 키 + docker 그룹 멤버십으로 대체.
- rsync 데몬 인증(포트 873)은 SSH와 별개 자격증명 체계라 그대로 유지 — 평문 저장 자체는
  기존과 동일(`deploy.config`가 git에 안 올라가는 전제).

## 후속 — WSL 실행 시 키 경로 깨짐
- 사용자가 `wsl ./deploy.sh`로 실행 → `DEPLOY_KEY=~/.ssh/id_ed25519_nas`가 WSL 홈
  (`/home/deitrihi`)에서 안 찾아져 `Permission denied` 재발.
- 원인: WSL 홈 디렉터리는 Git Bash 홈(`/mnt/c/Users/deitr`)과 별개 파일시스템 — 애초에
  WSL을 썼던 이유는 Git Bash에 `rsync`가 없어서(확인함) 245MB DB를 증분 전송하려던 것.
- 판단: 같은 LAN(`192.168.0.200`)이라 tar 전체 전송도 충분히 빨라 문제되지 않아, WSL 없이
  Git Bash로만 실행하기로 결정(사용자 선택 — WSL에도 키를 복제해 rsync 증분 전송을 유지하는
  대안도 제시했으나 미채택). `deploy.sh` 상단에 "WSL로 띄우지 말 것" 안내 주석 추가.

## 미해결
- 없음 — 요청한 "스크립트 한 번 실행으로 build까지" 목표를 실제 NAS 대상으로 확인 완료.
