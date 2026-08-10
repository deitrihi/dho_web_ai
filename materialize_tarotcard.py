#!/usr/bin/env python3
"""tarotCard 카테고리 전용 테이블 (입수 NPC는 공유 item_acquisition_npc_location 테이블에서 조회)"""
from pg_conn import connect


def init_tables(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
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
    conn = connect()
    init_tables(conn)

    with conn.cursor() as cur:
        cur.execute("SELECT item_id FROM items_core WHERE category = 'tarotCard'")
        item_ids = [r[0] for r in cur.fetchall()]
    print(f"[tarotCard] 대상: {len(item_ids)}건")

    skipped = set()
    cur = conn.cursor()
    for item_id in item_ids:
        cur.execute("SELECT name FROM items_core WHERE category = 'tarotCard' AND item_id = %s", (item_id,))
        name = cur.fetchone()[0]

        effect_text = None
        summary_text = None
        cur.execute(
            "SELECT label, text, links_json FROM raw_attrs WHERE category='tarotCard' AND item_id=%s",
            (item_id,),
        )
        for label, text, links_json in cur.fetchall():
            if label == "효과":
                effect_text = text
            elif label == "요약":
                summary_text = text
            else:
                skipped.add(f"ATTR:{label}")

        cur.execute(
            "INSERT INTO tarot_card VALUES (%s,%s,%s,%s)",
            (item_id, name, effect_text, summary_text),
        )

        cur.execute(
            "SELECT DISTINCT label FROM raw_tables WHERE category='tarotCard' AND item_id=%s", (item_id,)
        )
        for (label,) in cur.fetchall():
            if label != "입수 NPC":
                skipped.add(f"TABLE:{label}")

    cur.close()
    conn.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM tarot_card")
        n = cur.fetchone()[0]
    print(f"[tarotCard] 완료: {n}건 적재")
    if skipped:
        print("[tarotCard] 매핑 안 됨:", skipped)
    conn.close()


if __name__ == "__main__":
    materialize()
