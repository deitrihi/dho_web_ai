# DHO 아카이브 AI 검색 챗봇

`dho_structured.sqlite3`를 자연어 질문으로 조회하는 Text-to-SQL 챗봇 프론트엔드.
기존 `openwebui_tool_dho_sql.py`(OpenWebUI Tool 플러그인)를 대체하는, Vercel AI SDK 기반의
직접 구축한 프론트엔드다. Next.js(App Router) + `ai`/`@ai-sdk/react`/`@ai-sdk/openai`로
구현했고, `../dho_structured.sqlite3`를 Node.js 내장 `node:sqlite`(읽기 전용)로 직접 읽는다.

## 도구(Tool) 목록

`openwebui_tool_dho_sql.py`의 6개 함수를 `lib/dho-db.ts`로 그대로 포팅했다.

- `list_categories` — 70개 카테고리 이름 + 항목 수
- `get_item_detail` — 이름으로 검색해서 상세정보(획득 방법 포함) 한 번에 조회
- `search_items` — 이름으로 category/item_id만 가볍게 검색
- `find_tables` — 테이블 이름 검색
- `get_table_schema` — CREATE TABLE 구문 + 샘플 행 3개
- `run_sql` — SELECT 전용 쿼리 실행 (최대 200행)

## 실행

```bash
cp .env.local.example .env.local   # 값 채우기 (프로젝트 루트 .env.example과 같은 값 재사용 가능)
npm install
npm run dev                        # http://localhost:3000
```

`.env.local`에 필요한 값.

- `OPENAI_API_BASE_URL` — OpenAI 호환 API 엔드포인트
- `OPENAI_API_KEY`
- `OPENAI_MODEL` — 기본값 `gpt-5-mini`
- `DHO_DB_PATH` (선택) — `dho_structured.sqlite3` 경로, 기본값은 `../dho_structured.sqlite3`

## 참고

- API 라우트: `app/api/chat/route.ts` (Node.js 런타임 고정 — `node:sqlite` 때문에 Edge 불가)
- 채팅 UI: `app/page.tsx`
- DB 접근/도구 로직: `lib/dho-db.ts`

## Docker 배포 (NAS 등 원격 서버)

`Dockerfile`(Next.js standalone 빌드, node:24-alpine)과 프로젝트 루트의
`docker-compose.yml`로 배포한다. 로컬에서 `docker build`/`docker compose build chat`으로
빌드 성공, `docker run`으로 컨테이너 기동 + 실제 OpenAI API 엔드포인트까지 요청 도달하는
것까지 확인했다(플레이스홀더 키라 401만 확인, 실제 응답까지는 미검증).

### 1. 서버에 프로젝트 전체를 옮긴다

`dbsql/` 폴더 전체(코드 + `dho_structured.sqlite3`)가 필요하다. 이 프로젝트는 git
저장소가 아니므로 `rsync`/`scp`로 복사하거나, 평소 NAS에 파일을 옮기던 방법을 그대로
쓰면 된다. 예시(rsync, SSH):

```bash
rsync -avz --exclude 'chat/node_modules' --exclude 'chat/.next' \
  /c/dev/dho/dbsql/ user@nas-host:/path/to/dbsql/
```

`dho_structured.sqlite3`는 235MB 정도라 전송에 시간이 걸릴 수 있다. 이후 DB를
재스테이징할 때마다(예: `build_structured_db.py stage` 재실행) 이 파일만 다시
동기화해주면 됨.

### 2. 서버에서 `.env` 준비

`dbsql/` 루트(= `docker-compose.yml`이 있는 위치)에서.

```bash
cp .env.example .env
# .env를 열어서 OPENAI_API_BASE_URL/OPENAI_API_KEY/OPENAI_MODEL 값을 채운다
```

### 3. 빌드 + 기동

```bash
cd /path/to/dbsql
docker compose up -d --build chat
```

- `chat` 서비스가 `./chat`(Dockerfile 위치)을 빌드해서 `dho-chat` 컨테이너로 뜬다.
- `dbsql/` 폴더 전체를 컨테이너 안 `/data/dbsql`에 읽기 전용으로 마운트하므로,
  `dho_structured.sqlite3`를 다시 스테이징해도 컨테이너 재시작 없이 최신 파일을 그대로
  읽는다(볼륨 마운트라 파일 갱신이 바로 반영됨. 컨테이너 재빌드는 코드가 바뀔 때만
  필요).
- 기본 포트는 3000. 이미 3000을 쓰는 다른 서비스가 있으면 `docker-compose.yml`의
  `ports: ["3000:3000"]`를 원하는 호스트 포트로 바꾸면 된다(예: `"8090:3000"`).
- `restart: unless-stopped`가 설정돼 있어서 NAS 재부팅 시에도 자동으로 다시 뜬다.

### 4. 확인

```bash
docker compose logs -f chat     # 기동 로그 확인
curl http://localhost:3000/     # 200 OK면 정상
```

### 재배포(코드 변경 시)

```bash
docker compose up -d --build chat
```

기존 `dho-chat` 컨테이너를 내리고 새 이미지로 다시 띄운다. `--build`를 빼면 이미지
재빌드 없이 기존 이미지로 재시작만 한다.
