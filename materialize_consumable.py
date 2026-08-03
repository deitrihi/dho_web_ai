#!/usr/bin/env python3
"""consumable 카테고리 전용 테이블 (획득 방법은 공유 item_acquisition_* 테이블에서 조회)"""
import json
import sqlite3
from pathlib import Path

STRUCT_DB = Path(__file__).parent / "dho_structured.sqlite3"


def init_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS consumable;

        -- 획득 방법(판매NPC/레시피/아이템교환/직접판매)은 카테고리 무관 공유 테이블
        -- (item_acquisition_seller 등, WHERE category='consumable')에서 조회한다.
        CREATE TABLE consumable (
            item_id INTEGER PRIMARY KEY,
            name TEXT,
            category_type TEXT,
            usage_effect_text TEXT,
            usage_effect_item_id INTEGER
        );
        """
    )
    conn.commit()


def materialize() -> None:
    conn = sqlite3.connect(STRUCT_DB)
    init_tables(conn)

    item_ids = [r[0] for r in conn.execute("SELECT item_id FROM items_core WHERE category = 'consumable'")]
    print(f"[consumable] 대상: {len(item_ids)}건")

    skipped = set()
    for item_id in item_ids:
        name = conn.execute(
            "SELECT name FROM items_core WHERE category = 'consumable' AND item_id = ?", (item_id,)
        ).fetchone()[0]

        category_type = None
        usage_effect_text = None
        usage_effect_item_id = None
        for label, text, links_json in conn.execute(
            "SELECT label, text, links_json FROM raw_attrs WHERE category='consumable' AND item_id=?",
            (item_id,),
        ):
            links = json.loads(links_json)
            if label == "분류":
                category_type = text
            elif label == "사용효과":
                usage_effect_text = text
                usage_effect_item_id = links[0]["item_id"] if links else None
            else:
                skipped.add(f"ATTR:{label}")

        conn.execute(
            "INSERT INTO consumable VALUES (?,?,?,?,?)",
            (item_id, name, category_type, usage_effect_text, usage_effect_item_id),
        )

        for (label,) in conn.execute(
            "SELECT DISTINCT label FROM raw_tables WHERE category='consumable' AND item_id=?", (item_id,)
        ):
            if label != "획득 방법":  # build_acquisition.py가 이미 공유 테이블로 처리
                skipped.add(f"TABLE:{label}")

    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM consumable").fetchone()[0]
    print(f"[consumable] 완료: {n}건 적재")
    if skipped:
        print("[consumable] 매핑 안 됨:", skipped)
    conn.close()


if __name__ == "__main__":
    materialize()
