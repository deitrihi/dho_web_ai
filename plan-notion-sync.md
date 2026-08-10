# 노션 데이터 챗봇 검색 연동

## 배경
챗봇(`chat/`)은 현재 `dho_structured.sqlite3`(게임 위키 데이터, 211개 테이블)만 조회한다.
사용자가 노션에 관리 중인 문서(개인 메모 성격, 게임 위키 데이터와는 다른 종류)를 Notion API로
가져와서 같은 챗봇에서 검색할 수 있게 하고 싶어함.

## 목표
- 지정한 노션 상위 페이지 + 하위 페이지 전체를 Notion API로 읽어와 로컬 DB에 저장한다.
- 매일 1회 자동으로 재동기화한다.
- 챗봇이 이 데이터를 기존 아이템 검색과 같은 방식(FTS5)으로 검색할 수 있게 한다.

## 접근 방식
1. **저장 위치**: 기존 `dho_structured.sqlite3`에 새 테이블로 추가(사용자 선택).
   게임 위키 테이블과는 성격이 달라 `items_fts`에 섞지 않고 별도 테이블/인덱스로 분리.
   - `notion_pages` (page_id PK, parent_page_id, title, url, last_edited_time, content, synced_at)
   - `notion_fts` (FTS5 가상 테이블, trigram 토크나이저 — `items_fts`와 동일 패턴)
2. **동기화 스크립트**: `sync_notion.py` (신규)
   - Notion REST API를 `requests`로 직접 호출(scraper.py와 동일한 방식, notion-client
     패키지 의존성 추가 안 함).
   - 상위 페이지 URL/ID 인자로 받아 하위 페이지를 재귀적으로 전부 수집.
   - 블록을 순회하며 plain text로 변환해 `content` 컬럼에 저장.
   - 매 실행마다 전체 재적재(DELETE 후 INSERT) — 페이지 수가 적어(개인 문서) 증분 동기화는
     과설계로 판단.
3. **챗봇 연동**: `chat/lib/dho-db.ts`에 `searchNotion()` 추가, `route.ts`에 `search_notion`
   도구 등록. `items_fts`의 `findMatchingItems()`와 동일한 bm25 정렬 + 짧은 키워드 LIKE
   폴백 패턴을 따른다.
4. **스케줄링**: 사용자가 하루 1회를 선택. 이 저장소가 실제로 동작하는 곳은 개발 PC(Windows)이므로
   Windows 작업 스케줄러(`schtasks`)에 일 1회 작업 등록. NAS 배포본에 반영하려면 기존
   `deploy.sh`로 별도 전송 필요(이번 범위 밖, README에만 언급).

## 결정 사항
- `openwebui_tool_dho_sql.py`는 이미 사용 안 하는 레거시(README에 명시)라 손대지 않음.
- 노션 원본 URL은 개인적인 내용을 담고 있을 수 있어(`.env`/`dho_structured.sqlite3` 둘 다
  이미 `.gitignore` 대상 — 커밋 걱정 없음) 별도 마스킹 없이 그대로 저장.
