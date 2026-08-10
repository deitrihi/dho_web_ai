#!/usr/bin/env python3
"""
items_search(build_search_index.py가 만든 name/title/description/속성 통합 텍스트)를
OpenAI 임베딩 API로 벡터화해서 item_embeddings(pgvector)에 저장하는 스크립트.

chat의 시맨틱 검색(자연어로 비슷한 의미의 아이템 찾기)이 이 테이블을 조회한다. 키워드
검색(items_search, pg_trgm)과 역할이 다르므로 대체가 아니라 보완 — 정확한 이름을 모르거나
개념/느낌으로 찾을 때 시맨틱 검색이 유리하다.

이 스크립트는 DERIVED_PIPELINE_SCRIPTS(웹앱이 항목 저장마다 자동 재실행하는 목록)에
포함되지 않는다 — API 호출 비용/시간이 들어서 저장할 때마다 돌리기엔 부적합. 데이터가
크게 바뀌었을 때 수동으로 실행한다.

사용법
------
    python build_embeddings.py  (DATABASE_URL, OPENAI_API_KEY 환경변수 필요)
"""
import os
import time

import requests

from pg_conn import connect

OPENAI_API_BASE_URL = os.environ.get("OPENAI_API_BASE_URL", "https://api.openai.com/v1")
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
EMBEDDING_MODEL = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIMENSIONS = 1536  # text-embedding-3-small 기본 차원 — 모델을 바꾸면 스키마도 같이 바꿔야 함

BATCH_SIZE = 100  # 요청 1회당 아이템 수 (OpenAI 입력 배열 상한 2048보다 훨씬 보수적으로)
MAX_TEXT_CHARS = 6000  # 항목당 임베딩에 넣을 텍스트 상한(한글은 토큰/글자 비율이 높아 보수적으로 자름)
MAX_RETRIES = 3


def embed_batch(texts: list[str]) -> list[list[float]]:
    for attempt in range(1, MAX_RETRIES + 1):
        resp = requests.post(
            f"{OPENAI_API_BASE_URL}/embeddings",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={"model": EMBEDDING_MODEL, "input": texts},
            timeout=60,
        )
        if resp.status_code == 200:
            data = resp.json()["data"]
            return [d["embedding"] for d in data]
        if resp.status_code == 429 or resp.status_code >= 500:
            wait = 2**attempt
            print(f"[embeddings] {resp.status_code} 응답, {wait}초 대기 후 재시도 ({attempt}/{MAX_RETRIES})")
            time.sleep(wait)
            continue
        raise RuntimeError(f"OpenAI 임베딩 API 오류 {resp.status_code}: {resp.text[:500]}")
    raise RuntimeError(f"OpenAI 임베딩 API가 {MAX_RETRIES}회 재시도 후에도 실패")


def vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(repr(x) for x in vec) + "]"


def build() -> None:
    conn = connect()
    with conn.cursor() as cur:
        cur.execute(
            f"""
            DROP TABLE IF EXISTS item_embeddings;
            CREATE TABLE item_embeddings (
                category TEXT NOT NULL,
                item_id INTEGER NOT NULL,
                embedded_text TEXT NOT NULL,
                embedding vector({EMBEDDING_DIMENSIONS}) NOT NULL,
                PRIMARY KEY (category, item_id)
            );
            """
        )
    conn.commit()

    with conn.cursor() as cur:
        cur.execute("SELECT category, item_id, search_text FROM items_search ORDER BY category, item_id")
        rows = cur.fetchall()
    print(f"[embeddings] 대상: {len(rows)}건, 모델: {EMBEDDING_MODEL}")

    insert_cur = conn.cursor()
    done = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        texts = [(text or "")[:MAX_TEXT_CHARS] for _, _, text in batch]
        vectors = embed_batch(texts)
        for (category, item_id, text), vec in zip(batch, vectors):
            insert_cur.execute(
                "INSERT INTO item_embeddings (category, item_id, embedded_text, embedding) "
                "VALUES (%s, %s, %s, %s::vector)",
                (category, item_id, text[:MAX_TEXT_CHARS], vector_literal(vec)),
            )
        done += len(batch)
        print(f"[embeddings] {done}/{len(rows)}건 완료")
        conn.commit()
    insert_cur.close()

    with conn.cursor() as cur:
        # 코사인 거리 기준 HNSW 인덱스 — OpenAI 임베딩은 코사인 유사도 기준으로 쓰는 게 표준
        cur.execute("CREATE INDEX idx_item_embeddings_hnsw ON item_embeddings USING hnsw (embedding vector_cosine_ops)")
    conn.commit()
    conn.close()
    print("[embeddings] 완료")


if __name__ == "__main__":
    build()
