#!/usr/bin/env python3
"""Wiki.js 페이지 콘텐츠(wikidb.pages)를 헤더 기준으로 청킹해서 pgvector에 임베딩하는
스크립트. Wiki.js는 웹훅을 지원하지 않으므로(2026-08 확인, requarks/wiki 이슈 트래커에
기능 요청으로만 남아있음) 폴링 방식을 쓴다 — 매 실행마다 wikidb.pages.hash(Wiki.js가 저장
시점마다 갱신하는 콘텐츠 해시)를 wiki_chunk_sync_state와 비교해서 바뀐 페이지만 재청킹한다.

사람이 위키에서 직접 편집한 내용도 포함되어야 하므로, 콘텐츠는 항상 Wiki.js DB(wikidb)에서
읽어온다 — build_wikijs_pages.py가 생성한 마크다운을 재사용하지 않는다.

grounding: page_path가 "dho/<category>/<item_id>" 형식이면 category/item_id를 같이
저장해서, chat이 검색 결과를 DB 원본 레코드와 조인해 사실 근거로 삼을 수 있게 한다.
그 외(자유 위키 페이지, 예: 공략/개요 글)는 category/item_id가 NULL이고 청크 텍스트
자체가 근거가 된다.

청킹: 마크다운 헤더(#/##/###) 단위로 섹션을 나눈다 — build_wikijs_pages.py가 만드는
문서 구조("# 제목" + "## 속성" + "### <표 이름>" ...)와 맞춰서 설계했지만, 사람이 자유
페이지에 쓰는 임의의 헤더 구조에도 동일하게 동작한다. 임베딩 입력에는 페이지 제목을
접두어로 붙여 문맥을 보강한다(item_embeddings의 embedded_text 패턴과 동일).

사용법
------
    python build_wiki_chunks.py
    (DATABASE_URL, WIKI_DATABASE_URL, OPENAI_API_KEY 환경변수 필요)
    주기적 재실행(예: crontab)을 염두에 두고 설계됨 — 변경 없는 페이지는 건너뛴다.
"""
import os
import re
import time

import psycopg
import requests
from psycopg.rows import dict_row

DATABASE_URL = os.environ["DATABASE_URL"]
WIKI_DATABASE_URL = os.environ["WIKI_DATABASE_URL"]
OPENAI_API_BASE_URL = os.environ.get("OPENAI_API_BASE_URL", "https://api.openai.com/v1")
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
EMBEDDING_MODEL = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIMENSIONS = 1536  # text-embedding-3-small 기본 차원 — item_embeddings와 동일하게 맞춤

BATCH_SIZE = 100
MAX_TEXT_CHARS = 6000
MAX_RETRIES = 3

PAGE_PATH_RE = re.compile(r"^dho/([^/]+)/(\d+)$")
HEADING_RE = re.compile(r"^(#{1,3} .+)$", re.MULTILINE)


def chunk_markdown(content: str) -> list[str]:
    matches = list(HEADING_RE.finditer(content))
    if not matches:
        text = content.strip()
        return [text] if text else []
    chunks = []
    if matches[0].start() > 0:
        pre = content[: matches[0].start()].strip()
        if pre:
            chunks.append(pre)
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        chunk = content[m.start() : end].strip()
        if chunk:
            chunks.append(chunk)
    return chunks


def embed_batch(texts: list[str]) -> list[list[float]]:
    for attempt in range(1, MAX_RETRIES + 1):
        resp = requests.post(
            f"{OPENAI_API_BASE_URL}/embeddings",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={"model": EMBEDDING_MODEL, "input": texts},
            timeout=60,
        )
        if resp.status_code == 200:
            return [d["embedding"] for d in resp.json()["data"]]
        if resp.status_code == 429 or resp.status_code >= 500:
            wait = 2**attempt
            print(f"[wiki_chunks] {resp.status_code} 응답, {wait}초 대기 후 재시도 ({attempt}/{MAX_RETRIES})")
            time.sleep(wait)
            continue
        raise RuntimeError(f"OpenAI 임베딩 API 오류 {resp.status_code}: {resp.text[:500]}")
    raise RuntimeError(f"OpenAI 임베딩 API가 {MAX_RETRIES}회 재시도 후에도 실패")


def vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(repr(x) for x in vec) + "]"


def ensure_tables(db: psycopg.Connection) -> None:
    db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS wiki_chunks (
            id SERIAL PRIMARY KEY,
            page_path TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            category TEXT,
            item_id INTEGER,
            chunk_text TEXT NOT NULL,
            embedded_text TEXT NOT NULL,
            embedding vector({EMBEDDING_DIMENSIONS}) NOT NULL,
            UNIQUE (page_path, chunk_index)
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_wiki_chunks_category_item ON wiki_chunks (category, item_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_wiki_chunks_hnsw ON wiki_chunks USING hnsw (embedding vector_cosine_ops)")
    db.execute(
        "CREATE TABLE IF NOT EXISTS wiki_chunk_sync_state ("
        "page_path TEXT PRIMARY KEY, content_hash TEXT NOT NULL, synced_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    )
    db.commit()


def sync() -> None:
    dho_db = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    wiki_db = psycopg.connect(WIKI_DATABASE_URL, row_factory=dict_row)
    ensure_tables(dho_db)

    pages = wiki_db.execute("SELECT path, title, content, hash FROM pages ORDER BY path").fetchall()
    wiki_db.close()
    print(f"[wiki_chunks] Wiki.js 페이지 {len(pages)}건 확인")

    known_paths = {p["path"] for p in pages}
    state = {
        r["page_path"]: r["content_hash"]
        for r in dho_db.execute("SELECT page_path, content_hash FROM wiki_chunk_sync_state").fetchall()
    }

    removed_paths = set(state) - known_paths
    for path in removed_paths:
        dho_db.execute("DELETE FROM wiki_chunks WHERE page_path = %s", (path,))
        dho_db.execute("DELETE FROM wiki_chunk_sync_state WHERE page_path = %s", (path,))
    if removed_paths:
        dho_db.commit()
        print(f"[wiki_chunks] 삭제된 페이지 {len(removed_paths)}건 정리")

    changed = [p for p in pages if state.get(p["path"]) != p["hash"]]
    print(f"[wiki_chunks] 변경된 페이지 {len(changed)}건 재청킹")

    total_chunks = 0
    for page in changed:
        path = page["path"]
        m = PAGE_PATH_RE.match(path)
        category, item_id = (m.group(1), int(m.group(2))) if m else (None, None)

        chunks = chunk_markdown(page["content"] or "")
        dho_db.execute("DELETE FROM wiki_chunks WHERE page_path = %s", (path,))
        if chunks:
            embedded_texts = [f"{page['title']}\n\n{c}"[:MAX_TEXT_CHARS] for c in chunks]
            for batch_start in range(0, len(embedded_texts), BATCH_SIZE):
                batch = embedded_texts[batch_start : batch_start + BATCH_SIZE]
                vectors = embed_batch(batch)
                for offset, vec in enumerate(vectors):
                    idx = batch_start + offset
                    dho_db.execute(
                        "INSERT INTO wiki_chunks (page_path, chunk_index, category, item_id, chunk_text, embedded_text, embedding) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s::vector)",
                        (path, idx, category, item_id, chunks[idx][:MAX_TEXT_CHARS], embedded_texts[idx], vector_literal(vec)),
                    )
        dho_db.execute(
            "INSERT INTO wiki_chunk_sync_state (page_path, content_hash) VALUES (%s, %s) "
            "ON CONFLICT (page_path) DO UPDATE SET content_hash = EXCLUDED.content_hash, synced_at = now()",
            (path, page["hash"]),
        )
        dho_db.commit()
        total_chunks += len(chunks)

    dho_db.close()
    print(f"[wiki_chunks] 완료 — 페이지 {len(changed)}건, 청크 {total_chunks}건")


if __name__ == "__main__":
    sync()
