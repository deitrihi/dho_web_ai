#!/usr/bin/env python3
"""
챗봇(search_items/get_item_detail/get_backlinks)의 키워드 검색을 위한 트라이그램 검색
인덱스(items_search)를 만드는 스크립트. items_core(이름/제목/설명) + raw_attrs(속성
라벨/값, 항목별로 이어붙임)를 대상으로 한다.

SQLite FTS5(trigram 토크나이저) 대신 PostgreSQL의 pg_trgm 확장(GIN 트라이그램 인덱스)을
쓴다 — 기존과 동일하게 부분일치 검색이 되고, ILIKE '%keyword%' 쿼리를 그대로 가속해준다.
아주 짧은 키워드(1~2글자)는 트라이그램 인덱스 효율이 떨어지므로 호출부(chat/lib/dho-db.ts)에서
기존과 동일하게 LIKE 방식으로 폴백한다.

사용법
------
    python build_search_index.py  (DATABASE_URL 환경변수 필요)
"""
from pg_conn import connect


def build() -> None:
    conn = connect()
    with conn.cursor() as cur:
        cur.execute(
            """
            DROP TABLE IF EXISTS items_search;
            CREATE TABLE items_search (
                category TEXT NOT NULL,
                item_id INTEGER NOT NULL,
                name TEXT,
                title TEXT,
                search_text TEXT,
                PRIMARY KEY (category, item_id)
            );
            """
        )

        cur.execute(
            """
            INSERT INTO items_search (category, item_id, name, title, search_text)
            SELECT
                ic.category,
                ic.item_id,
                ic.name,
                ic.title,
                COALESCE(ic.name, '') || ' ' || COALESCE(ic.title, '') || ' ' ||
                COALESCE(ic.description, '') || ' ' ||
                COALESCE((
                    SELECT STRING_AGG(ra.label || ' ' || COALESCE(ra.text, ''), ' ')
                    FROM raw_attrs ra
                    WHERE ra.category = ic.category AND ra.item_id = ic.item_id
                ), '')
            FROM items_core ic
            """
        )

        cur.execute("CREATE INDEX idx_items_search_trgm ON items_search USING GIN (search_text gin_trgm_ops)")

        cur.execute("SELECT count(*) FROM items_search")
        count = cur.fetchone()[0]

    conn.commit()
    conn.close()
    print(f"[search_index] items_search 적재: {count}건")
    print("[search_index] 완료")


if __name__ == "__main__":
    build()
