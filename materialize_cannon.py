#!/usr/bin/env python3
"""
raw_attrs/raw_tables 스테이징 데이터를 cannon 전용 테이블로 옮기는 스크립트
(카테고리별 전용 테이블 방식의 파일럿 — 다른 카테고리도 이 패턴을 따라 확장)
"""
import json
import os
import re
import sqlite3
from pathlib import Path

# DHO_DB_PATH로 오버라이드 가능 (dho_webapp.py/chat과 동일한 관례)
STRUCT_DB = Path(os.environ.get("DHO_DB_PATH", str(Path(__file__).parent / "dho_structured.sqlite3")))

ATTR_COLUMNS = {
    "분류": "category_type",
    "포탄 종류": "ammo_type",
    "내구도": "durability",
    "관통력": "penetration",
    "사정거리": "range",
    "포탄속도": "ball_speed",
    "작렬범위": "blast_radius",
    "장전속도": "reload_speed",
}
INT_COLUMNS = {"durability", "penetration", "range", "ball_speed", "blast_radius", "reload_speed"}


def init_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS cannon;
        DROP TABLE IF EXISTS cannon_seller;
        DROP TABLE IF EXISTS cannon_transmutation_policy;
        DROP TABLE IF EXISTS cannon_transmutation_skill;
        DROP TABLE IF EXISTS cannon_transmutation_material;

        CREATE TABLE cannon (
            item_id INTEGER PRIMARY KEY,
            name TEXT,
            category_type TEXT,
            ammo_type TEXT,
            durability INTEGER,
            penetration INTEGER,
            range INTEGER,
            ball_speed INTEGER,
            blast_radius INTEGER,
            reload_speed INTEGER
        );

        -- 획득 방법 표 (판매 NPC / 지역 / 장소) 를 펼친 것. 장소 한 셀에 여러 도시가 들어있으면
        -- 도시별로 행을 분리한다.
        CREATE TABLE cannon_seller (
            item_id INTEGER,
            seller_npc TEXT,
            region TEXT,
            place_name TEXT,
            place_category TEXT,
            place_item_id INTEGER
        );

        -- 변성연금 표 (정책 1건당 스킬/재료 요건은 각각 독립적인 목록이라 교차곱하지 않고
        -- 별도 연결 테이블로 분리한다: 스킬은 "이 중 하나 이상 충족", 재료는 "전부 필요")
        CREATE TABLE cannon_transmutation_policy (
            item_id INTEGER,
            policy_name TEXT,
            policy_item_id INTEGER
        );
        CREATE TABLE cannon_transmutation_skill (
            item_id INTEGER,
            policy_item_id INTEGER,
            skill_name TEXT,
            skill_item_id INTEGER,
            skill_level INTEGER
        );
        CREATE TABLE cannon_transmutation_material (
            item_id INTEGER,
            policy_item_id INTEGER,
            material_name TEXT,
            material_category TEXT,
            material_item_id INTEGER,
            material_qty INTEGER
        );
        """
    )
    conn.commit()


def parse_name_qty_pairs(text: str, links: list[dict]) -> list[dict]:
    """'이름\\n수량,\\n이름\\n수량' 형태의 셀 텍스트를 링크 목록과 짝지어 구조화한다."""
    segments = [s.strip() for s in text.split(",")]
    results = []
    for i, seg in enumerate(segments):
        if not seg:
            continue
        parts = seg.split("\n")
        qty = None
        if len(parts) >= 2 and re.fullmatch(r"\d+", parts[-1].strip()):
            qty = int(parts[-1].strip())
        link = links[i] if i < len(links) else None
        results.append(
            {
                "name": link["text"] if link else parts[0].strip(),
                "category": link["category"] if link else None,
                "item_id": link["item_id"] if link else None,
                "qty": qty,
            }
        )
    return results


def materialize() -> None:
    conn = sqlite3.connect(STRUCT_DB)
    init_tables(conn)

    item_ids = [r[0] for r in conn.execute("SELECT item_id FROM items_core WHERE category = 'cannon'")]
    print(f"[cannon] 대상: {len(item_ids)}건")

    skipped_attrs = set()
    for item_id in item_ids:
        name = conn.execute(
            "SELECT name FROM items_core WHERE category = 'cannon' AND item_id = ?", (item_id,)
        ).fetchone()[0]

        cols = {"item_id": item_id, "name": name}
        for label, text, _links in conn.execute(
            "SELECT label, text, links_json FROM raw_attrs WHERE category='cannon' AND item_id=?",
            (item_id,),
        ):
            col = ATTR_COLUMNS.get(label)
            if not col:
                skipped_attrs.add(label)
                continue
            if col in INT_COLUMNS:
                m = re.search(r"-?\d+", text)
                cols[col] = int(m.group()) if m else None
            else:
                cols[col] = text

        col_names = list(cols.keys())
        placeholders = ",".join("?" * len(col_names))
        conn.execute(
            f"INSERT INTO cannon ({','.join(col_names)}) VALUES ({placeholders})",
            [cols[c] for c in col_names],
        )

        for label, headers_json, rows_json in conn.execute(
            "SELECT label, headers_json, rows_json FROM raw_tables WHERE category='cannon' AND item_id=?",
            (item_id,),
        ):
            headers = json.loads(headers_json)
            rows = json.loads(rows_json)

            if label == "획득 방법" and headers == ["판매 NPC", "지역", "장소"]:
                for row in rows:
                    seller, region, place = row[0]["text"], row[1]["text"], row[2]
                    if place["links"]:
                        for link in place["links"]:
                            conn.execute(
                                "INSERT INTO cannon_seller VALUES (?,?,?,?,?,?)",
                                (item_id, seller, region, link["text"], link["category"], link["item_id"]),
                            )
                    else:
                        for place_name in [p.strip() for p in place["text"].split(",")]:
                            conn.execute(
                                "INSERT INTO cannon_seller VALUES (?,?,?,?,?,?)",
                                (item_id, seller, region, place_name, None, None),
                            )

            elif label == "변성연금" and headers == ["정책", "스킬", "재료"]:
                for row in rows:
                    policy_cell, skill_cell, material_cell = row
                    policy_link = policy_cell["links"][0] if policy_cell["links"] else None
                    policy_item_id = policy_link["item_id"] if policy_link else None
                    conn.execute(
                        "INSERT INTO cannon_transmutation_policy VALUES (?,?,?)",
                        (item_id, policy_cell["text"], policy_item_id),
                    )
                    for skill in parse_name_qty_pairs(skill_cell["text"], skill_cell["links"]):
                        conn.execute(
                            "INSERT INTO cannon_transmutation_skill VALUES (?,?,?,?,?)",
                            (item_id, policy_item_id, skill["name"], skill["item_id"], skill["qty"]),
                        )
                    for material in parse_name_qty_pairs(material_cell["text"], material_cell["links"]):
                        conn.execute(
                            "INSERT INTO cannon_transmutation_material VALUES (?,?,?,?,?,?)",
                            (
                                item_id,
                                policy_item_id,
                                material["name"],
                                material["category"],
                                material["item_id"],
                                material["qty"],
                            ),
                        )
            else:
                skipped_attrs.add(f"TABLE:{label}:{headers}")

    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM cannon").fetchone()[0]
    print(f"[cannon] 완료: {n}건 적재")
    if skipped_attrs:
        print("[cannon] 매핑 안 된 label/표 (검토 필요):", skipped_attrs)
    conn.close()


if __name__ == "__main__":
    materialize()
