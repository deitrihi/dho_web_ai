#!/usr/bin/env python3
"""recipe 카테고리 전용 테이블 (필요 재료/스킬은 공유 item_detail_list 테이블에서 조회)"""
import json
import re
import sqlite3
from pathlib import Path

STRUCT_DB = Path(__file__).parent / "dho_structured.sqlite3"


def init_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS recipe;
        DROP TABLE IF EXISTS recipe_product;

        CREATE TABLE recipe (
            item_id INTEGER PRIMARY KEY,
            name TEXT,
            category_type TEXT,
            recipe_book_name TEXT,
            recipe_book_item_id INTEGER
        );

        -- 생산품 표 (결과/생산품/수량). "필요"(스킬/재료)는 item_detail_list에서
        -- category='recipe' AND type_text IN ('스킬','재료')로 조회한다.
        CREATE TABLE recipe_product (
            item_id INTEGER,
            result_text TEXT,
            product_name TEXT,
            product_category TEXT,
            product_item_id INTEGER,
            qty INTEGER
        );
        """
    )
    conn.commit()


def materialize() -> None:
    conn = sqlite3.connect(STRUCT_DB)
    init_tables(conn)

    item_ids = [r[0] for r in conn.execute("SELECT item_id FROM items_core WHERE category = 'recipe'")]
    print(f"[recipe] 대상: {len(item_ids)}건")

    skipped = set()
    for item_id in item_ids:
        name = conn.execute(
            "SELECT name FROM items_core WHERE category = 'recipe' AND item_id = ?", (item_id,)
        ).fetchone()[0]

        category_type = None
        recipe_book_name = None
        recipe_book_item_id = None
        for label, text, links_json in conn.execute(
            "SELECT label, text, links_json FROM raw_attrs WHERE category='recipe' AND item_id=?", (item_id,)
        ):
            links = json.loads(links_json)
            if label == "분류":
                category_type = text
            elif label == "레시피 책":
                recipe_book_name = text
                recipe_book_item_id = links[0]["item_id"] if links else None
            else:
                skipped.add(f"ATTR:{label}")

        conn.execute(
            "INSERT INTO recipe VALUES (?,?,?,?,?)",
            (item_id, name, category_type, recipe_book_name, recipe_book_item_id),
        )

        for label, headers_json, rows_json in conn.execute(
            "SELECT label, headers_json, rows_json FROM raw_tables WHERE category='recipe' AND item_id=?",
            (item_id,),
        ):
            headers = json.loads(headers_json)
            rows = json.loads(rows_json)
            if headers == ["결과", "생산품", "수량"]:
                for row in rows:
                    if len(row) != 3:
                        continue
                    result_cell, product_cell, qty_cell = row
                    product_link = product_cell["links"][0] if product_cell["links"] else None
                    qty_m = re.search(r"\d+", qty_cell["text"])
                    conn.execute(
                        "INSERT INTO recipe_product VALUES (?,?,?,?,?,?)",
                        (
                            item_id,
                            result_cell["text"],
                            product_cell["text"],
                            product_link["category"] if product_link else None,
                            product_link["item_id"] if product_link else None,
                            int(qty_m.group()) if qty_m else None,
                        ),
                    )
            elif label != "필요":  # 필요=종류/내용은 이미 build_acquisition.py가 item_detail_list로 처리함
                skipped.add(f"TABLE:{label}:{headers}")

    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM recipe").fetchone()[0]
    print(f"[recipe] 완료: {n}건 적재")
    if skipped:
        print("[recipe] 매핑 안 됨:", skipped)
    conn.close()


if __name__ == "__main__":
    materialize()
