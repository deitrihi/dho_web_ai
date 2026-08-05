#!/usr/bin/env python3
"""
챗봇(search_items/get_item_detail/get_backlinks)의 키워드 검색을 위한 FTS5 전문검색
인덱스(items_fts)를 만드는 스크립트. items_core(이름/제목/설명) + raw_attrs(속성
라벨/값, 항목별로 이어붙임)를 대상으로 한다.

trigram 토크나이저를 써서 기존 `LIKE '%keyword%'`와 동일한 부분일치 검색이 되도록
했다 — 단, trigram은 최소 3글자부터 인덱싱되므로 그보다 짧은 키워드는 호출부
(chat/lib/dho-db.ts)에서 기존 LIKE 방식으로 폴백한다.

사용법
------
    python build_search_index.py
"""
import os
import sqlite3
from pathlib import Path

# DHO_DB_PATH로 오버라이드 가능 (다른 파이프라인 스크립트와 동일한 관례)
STRUCT_DB = Path(os.environ.get("DHO_DB_PATH", str(Path(__file__).parent / "dho_structured.sqlite3")))


def build() -> None:
    conn = sqlite3.connect(STRUCT_DB)
    conn.executescript(
        """
        DROP TABLE IF EXISTS items_fts;
        CREATE VIRTUAL TABLE items_fts USING fts5(
            category UNINDEXED,
            item_id UNINDEXED,
            name,
            title,
            description,
            attrs_text,
            tokenize = 'trigram'
        );
        """
    )

    conn.execute(
        """
        INSERT INTO items_fts (category, item_id, name, title, description, attrs_text)
        SELECT
            ic.category,
            ic.item_id,
            ic.name,
            ic.title,
            ic.description,
            (
                SELECT GROUP_CONCAT(ra.label || ' ' || COALESCE(ra.text, ''), ' ')
                FROM raw_attrs ra
                WHERE ra.category = ic.category AND ra.item_id = ic.item_id
            )
        FROM items_core ic
        """
    )

    count = conn.execute("SELECT count(*) FROM items_fts").fetchone()[0]
    print(f"[search_index] items_fts 적재: {count}건")

    conn.commit()
    conn.close()
    print("[search_index] 완료")


if __name__ == "__main__":
    build()
