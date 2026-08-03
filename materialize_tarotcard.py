#!/usr/bin/env python3
"""tarotCard 카테고리 전용 테이블 (입수 NPC는 공유 item_acquisition_npc_location 테이블에서 조회)"""
import sqlite3
from pathlib import Path

STRUCT_DB = Path(__file__).parent / "dho_structured.sqlite3"


def init_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS tarot_card;

        -- 입수 NPC(지역/도시/도시 인물)는 item_acquisition_npc_location에서
        -- category='tarotCard'로 조회한다 (build_acquisition.py가 헤더 모양으로 이미 처리).
        CREATE TABLE tarot_card (
            item_id INTEGER PRIMARY KEY,
            name TEXT,
            effect_text TEXT,
            summary_text TEXT
        );
        """
    )
    conn.commit()


def materialize() -> None:
    conn = sqlite3.connect(STRUCT_DB)
    init_tables(conn)

    item_ids = [r[0] for r in conn.execute("SELECT item_id FROM items_core WHERE category = 'tarotCard'")]
    print(f"[tarotCard] 대상: {len(item_ids)}건")

    skipped = set()
    for item_id in item_ids:
        name = conn.execute(
            "SELECT name FROM items_core WHERE category = 'tarotCard' AND item_id = ?", (item_id,)
        ).fetchone()[0]

        effect_text = None
        summary_text = None
        for label, text, links_json in conn.execute(
            "SELECT label, text, links_json FROM raw_attrs WHERE category='tarotCard' AND item_id=?",
            (item_id,),
        ):
            if label == "효과":
                effect_text = text
            elif label == "요약":
                summary_text = text
            else:
                skipped.add(f"ATTR:{label}")

        conn.execute(
            "INSERT INTO tarot_card VALUES (?,?,?,?)",
            (item_id, name, effect_text, summary_text),
        )

        for (label,) in conn.execute(
            "SELECT DISTINCT label FROM raw_tables WHERE category='tarotCard' AND item_id=?", (item_id,)
        ):
            if label != "입수 NPC":
                skipped.add(f"TABLE:{label}")

    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM tarot_card").fetchone()[0]
    print(f"[tarotCard] 완료: {n}건 적재")
    if skipped:
        print("[tarotCard] 매핑 안 됨:", skipped)
    conn.close()


if __name__ == "__main__":
    materialize()
