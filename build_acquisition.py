#!/usr/bin/env python3
"""
raw_tables 스테이징에서 "획득 방법"류 표(카테고리 무관, 헤더 모양으로 판별)를 뽑아
모든 카테고리가 공유하는 item_acquisition_* 테이블로 옮기는 스크립트.

같은 헤더 모양(예: 지역/도시/도시 인물)이 label만 다르게 여러 카테고리에서 반복되는 것을
확인했기 때문에, label이 아니라 헤더 모양으로 매핑을 판별한다.
"""
import json
import os
import re
import sqlite3
from pathlib import Path

# DHO_DB_PATH로 오버라이드 가능 (dho_webapp.py/chat과 동일한 관례)
STRUCT_DB = Path(os.environ.get("DHO_DB_PATH", str(Path(__file__).parent / "dho_structured.sqlite3")))

# materialize_generic.py가 "이미 공유 테이블로 처리된 표 모양"을 걸러낼 때 참조한다.
# materialize() 아래 분기와 반드시 맞춰서 유지할 것.
COVERED_HEADER_SHAPES = {
    ("판매 NPC", "지역", "장소"),
    ("레시피 책", "레시피", "스킬", "재료"),
    ("정책", "스킬", "재료"),
    ("스킬", "재료", "정책", "기본소재"),
    ("해상 NPC", "함대 수", "특징", "해역"),
    ("해상 NPC", "함대 수", "해역"),
    ("보물지도", "목적지"),
    ("목적지", "퀘스트"),
    ("지역", "도시", "도시 인물"),
    ("아이템",),
    ("판매기간", "수량", "가격"),
    ("종류", "내용"),
}


def parse_name_qty_pairs(text: str, links: list[dict]) -> list[dict]:
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


def split_multi_links(cell: dict) -> list[dict]:
    """'런던,뤼베크,...' 처럼 한 셀에 여러 항목이 들어있으면 항목별로 분리한다."""
    if cell["links"]:
        return [{"name": l["text"], "category": l["category"], "item_id": l["item_id"]} for l in cell["links"]]
    parts = [p.strip() for p in cell["text"].split(",") if p.strip()]
    return [{"name": p, "category": None, "item_id": None} for p in parts] or [
        {"name": cell["text"], "category": None, "item_id": None}
    ]


def split_multi_links_with_qty(cell: dict) -> list[dict]:
    """split_multi_links()와 같은 역할이되, "탐색 1, 고고학 2"처럼 링크 이름 뒤에 수량/랭크가
    붙어있으면 그것도 뽑아낸다(item_detail_list의 '종류/내용' 표 전용 — 필요 스킬 랭크,
    보상 아이템 개수 등). 콤마로 나눈 세그먼트 수가 링크 수와 같고 각 세그먼트가 해당
    링크의 텍스트로 시작할 때만 신뢰하고 뽑는다 — 던전/퀘스트 "필요"의 연결된 퀘스트
    설명처럼 자유 텍스트에 링크가 여러 개 섞인 예외적인 셀(전체의 약 12%)은 이 조건이
    깨지므로 안전하게 수량 없이 이름만 반환한다(split_multi_links()와 동일한 동작)."""
    links = cell["links"]
    if not links:
        parts = [p.strip() for p in cell["text"].split(",") if p.strip()]
        return [{"name": p, "category": None, "item_id": None, "qty": None} for p in parts] or [
            {"name": cell["text"], "category": None, "item_id": None, "qty": None}
        ]

    segments = [s.strip() for s in cell["text"].split(",")]
    if len(segments) == len(links) and all(
        seg.startswith(link["text"]) for seg, link in zip(segments, links)
    ):
        results = []
        for seg, link in zip(segments, links):
            suffix = seg[len(link["text"]):].strip()
            qty = int(suffix) if re.fullmatch(r"\d+", suffix) else None
            results.append(
                {"name": link["text"], "category": link["category"], "item_id": link["item_id"], "qty": qty}
            )
        return results

    return [
        {"name": l["text"], "category": l["category"], "item_id": l["item_id"], "qty": None} for l in links
    ]


def init_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS item_acquisition_seller;
        DROP TABLE IF EXISTS item_acquisition_recipe;
        DROP TABLE IF EXISTS item_acquisition_recipe_skill;
        DROP TABLE IF EXISTS item_acquisition_recipe_material;
        DROP TABLE IF EXISTS item_transmutation_policy;
        DROP TABLE IF EXISTS item_transmutation_skill;
        DROP TABLE IF EXISTS item_transmutation_material;
        DROP TABLE IF EXISTS item_acquisition_marine_npc;
        DROP TABLE IF EXISTS item_acquisition_marine_npc_sea;
        DROP TABLE IF EXISTS item_acquisition_treasuremap;
        DROP TABLE IF EXISTS item_acquisition_quest;
        DROP TABLE IF EXISTS item_acquisition_npc_location;
        DROP TABLE IF EXISTS item_acquisition_from_item;
        DROP TABLE IF EXISTS item_acquisition_directsale;
        DROP TABLE IF EXISTS item_detail_list;
        DROP TABLE IF EXISTS item_acquisition_unmapped;

        CREATE TABLE item_acquisition_seller (
            category TEXT, item_id INTEGER, source_label TEXT,
            seller_npc TEXT, region TEXT,
            place_name TEXT, place_category TEXT, place_item_id INTEGER
        );

        CREATE TABLE item_acquisition_recipe (
            category TEXT, item_id INTEGER, source_label TEXT,
            recipe_book_name TEXT, recipe_book_item_id INTEGER,
            recipe_name TEXT, recipe_item_id INTEGER
        );
        CREATE TABLE item_acquisition_recipe_skill (
            category TEXT, item_id INTEGER, recipe_item_id INTEGER,
            skill_name TEXT, skill_item_id INTEGER, skill_level INTEGER
        );
        CREATE TABLE item_acquisition_recipe_material (
            category TEXT, item_id INTEGER, recipe_item_id INTEGER,
            material_name TEXT, material_category TEXT, material_item_id INTEGER, material_qty INTEGER
        );

        -- '변성연금'(정책/스킬/재료) 및 '획득 방법'(스킬/재료/정책/기본소재) 두 표 모양 모두 여기로 통합
        CREATE TABLE item_transmutation_policy (
            category TEXT, item_id INTEGER, source_label TEXT,
            policy_name TEXT, policy_item_id INTEGER,
            base_material_name TEXT, base_material_category TEXT, base_material_item_id INTEGER
        );
        CREATE TABLE item_transmutation_skill (
            category TEXT, item_id INTEGER, policy_item_id INTEGER,
            skill_name TEXT, skill_item_id INTEGER, skill_level INTEGER
        );
        CREATE TABLE item_transmutation_material (
            category TEXT, item_id INTEGER, policy_item_id INTEGER,
            material_name TEXT, material_category TEXT, material_item_id INTEGER, material_qty INTEGER
        );

        CREATE TABLE item_acquisition_marine_npc (
            category TEXT, item_id INTEGER, source_label TEXT,
            npc_name TEXT, npc_item_id INTEGER, fleet_count TEXT, feature_text TEXT
        );
        CREATE TABLE item_acquisition_marine_npc_sea (
            category TEXT, item_id INTEGER, npc_item_id INTEGER,
            sea_name TEXT, sea_item_id INTEGER
        );

        CREATE TABLE item_acquisition_treasuremap (
            category TEXT, item_id INTEGER, source_label TEXT,
            treasuremap_name TEXT, treasuremap_item_id INTEGER, requirement_text TEXT,
            destination_name TEXT, destination_category TEXT, destination_item_id INTEGER
        );

        CREATE TABLE item_acquisition_quest (
            category TEXT, item_id INTEGER, source_label TEXT,
            sea_name TEXT, sea_item_id INTEGER,
            quest_name TEXT, quest_item_id INTEGER,
            city_name TEXT, city_item_id INTEGER,
            detail_text TEXT
        );

        CREATE TABLE item_acquisition_npc_location (
            category TEXT, item_id INTEGER, source_label TEXT,
            region TEXT, city_name TEXT, city_item_id INTEGER,
            npc_name TEXT, npc_item_id INTEGER, npc_category TEXT
        );

        CREATE TABLE item_acquisition_from_item (
            category TEXT, item_id INTEGER, source_label TEXT,
            source_name TEXT, source_category TEXT, source_item_id INTEGER
        );

        -- 캐시샵류 직접 판매 (판매기간/수량/가격)
        CREATE TABLE item_acquisition_directsale (
            category TEXT, item_id INTEGER, source_label TEXT,
            sale_period TEXT, qty INTEGER, price_krw INTEGER
        );

        -- '종류/내용' 2열 표 (필요/보상/연결된 장소 등 다수 섹션이 공유하는 가장 흔한 모양).
        -- source_label로 어떤 섹션(필요/보상/...)이었는지 구분한다. content_qty는 원본 셀
        -- 텍스트에 "이름 수량"처럼 링크 뒤에 붙어있던 숫자(필요 스킬 랭크, 보상 아이템
        -- 개수 등) — 패턴이 안 맞는 예외적인 셀(자유 텍스트에 링크가 섞인 경우 등)은 NULL.
        CREATE TABLE item_detail_list (
            category TEXT, item_id INTEGER, source_label TEXT,
            type_text TEXT,
            content_name TEXT, content_category TEXT, content_item_id INTEGER,
            content_qty INTEGER
        );

        -- 아직 매핑 안 된 표 모양 (검토용 원본 보존)
        CREATE TABLE item_acquisition_unmapped (
            category TEXT, item_id INTEGER, label TEXT, headers_json TEXT, rows_json TEXT
        );
        """
    )
    conn.commit()


def materialize() -> None:
    conn = sqlite3.connect(STRUCT_DB)
    init_tables(conn)

    stats = {}

    def bump(shape):
        stats[shape] = stats.get(shape, 0) + 1

    malformed = 0
    for category, item_id, label, headers_json, rows_json in conn.execute(
        "SELECT category, item_id, label, headers_json, rows_json FROM raw_tables"
    ):
        headers = tuple(json.loads(headers_json))
        rows_all = json.loads(rows_json)
        # 중첩 rowspan 등으로 셀 개수가 헤더 수와 안 맞는(파싱이 부정확한) 행은 걸러내고
        # unmapped에 원본을 보존한다. (예: quest '필요' 표의 '택일' 대체 옵션 중첩 구조)
        rows = [r for r in rows_all if len(r) == len(headers)]
        if len(rows) != len(rows_all):
            malformed += len(rows_all) - len(rows)
            conn.execute(
                "INSERT INTO item_acquisition_unmapped VALUES (?,?,?,?,?)",
                (category, item_id, f"{label} (행 길이 불일치, 원본 보존)", headers_json, rows_json),
            )
        if not rows:
            continue

        if headers == ("판매 NPC", "지역", "장소"):
            bump("seller")
            for row in rows:
                seller, region, place = row[0]["text"], row[1]["text"], row[2]
                for p in split_multi_links(place):
                    conn.execute(
                        "INSERT INTO item_acquisition_seller VALUES (?,?,?,?,?,?,?,?)",
                        (category, item_id, label, seller, region, p["name"], p["category"], p["item_id"]),
                    )

        elif headers == ("레시피 책", "레시피", "스킬", "재료"):
            bump("recipe")
            for row in rows:
                book_cell, recipe_cell, skill_cell, material_cell = row
                book_link = book_cell["links"][0] if book_cell["links"] else None
                recipe_link = recipe_cell["links"][0] if recipe_cell["links"] else None
                recipe_item_id = recipe_link["item_id"] if recipe_link else None
                conn.execute(
                    "INSERT INTO item_acquisition_recipe VALUES (?,?,?,?,?,?,?)",
                    (
                        category, item_id, label,
                        book_cell["text"], book_link["item_id"] if book_link else None,
                        recipe_cell["text"], recipe_item_id,
                    ),
                )
                for skill in parse_name_qty_pairs(skill_cell["text"], skill_cell["links"]):
                    conn.execute(
                        "INSERT INTO item_acquisition_recipe_skill VALUES (?,?,?,?,?,?)",
                        (category, item_id, recipe_item_id, skill["name"], skill["item_id"], skill["qty"]),
                    )
                for material in parse_name_qty_pairs(material_cell["text"], material_cell["links"]):
                    conn.execute(
                        "INSERT INTO item_acquisition_recipe_material VALUES (?,?,?,?,?,?,?)",
                        (
                            category, item_id, recipe_item_id, material["name"],
                            material["category"], material["item_id"], material["qty"],
                        ),
                    )

        elif headers == ("정책", "스킬", "재료") or headers == ("스킬", "재료", "정책", "기본소재"):
            bump("transmutation")
            for row in rows:
                if headers == ("정책", "스킬", "재료"):
                    policy_cell, skill_cell, material_cell = row
                    base_cell = None
                else:
                    skill_cell, material_cell, policy_cell, base_cell = row
                policy_link = policy_cell["links"][0] if policy_cell["links"] else None
                policy_item_id = policy_link["item_id"] if policy_link else None
                base_link = base_cell["links"][0] if base_cell and base_cell["links"] else None
                conn.execute(
                    "INSERT INTO item_transmutation_policy VALUES (?,?,?,?,?,?,?,?)",
                    (
                        category, item_id, label, policy_cell["text"], policy_item_id,
                        base_cell["text"] if base_cell else None,
                        base_link["category"] if base_link else None,
                        base_link["item_id"] if base_link else None,
                    ),
                )
                for skill in parse_name_qty_pairs(skill_cell["text"], skill_cell["links"]):
                    conn.execute(
                        "INSERT INTO item_transmutation_skill VALUES (?,?,?,?,?,?)",
                        (category, item_id, policy_item_id, skill["name"], skill["item_id"], skill["qty"]),
                    )
                for material in parse_name_qty_pairs(material_cell["text"], material_cell["links"]):
                    conn.execute(
                        "INSERT INTO item_transmutation_material VALUES (?,?,?,?,?,?,?)",
                        (
                            category, item_id, policy_item_id, material["name"],
                            material["category"], material["item_id"], material["qty"],
                        ),
                    )

        elif headers in (("해상 NPC", "함대 수", "특징", "해역"), ("해상 NPC", "함대 수", "해역")):
            bump("marine_npc")
            for row in rows:
                if len(row) == 4:
                    npc_cell, fleet_cell, feature_cell, sea_cell = row
                else:
                    npc_cell, fleet_cell, sea_cell = row
                    feature_cell = None
                npc_link = npc_cell["links"][0] if npc_cell["links"] else None
                npc_item_id = npc_link["item_id"] if npc_link else None
                conn.execute(
                    "INSERT INTO item_acquisition_marine_npc VALUES (?,?,?,?,?,?,?)",
                    (
                        category, item_id, label, npc_cell["text"], npc_item_id,
                        fleet_cell["text"], feature_cell["text"] if feature_cell else None,
                    ),
                )
                for sea in split_multi_links(sea_cell):
                    conn.execute(
                        "INSERT INTO item_acquisition_marine_npc_sea VALUES (?,?,?,?,?)",
                        (category, item_id, npc_item_id, sea["name"], sea["item_id"]),
                    )

        elif headers == ("보물지도", "목적지"):
            bump("treasuremap")
            for row in rows:
                map_cell, dest_cell = row
                map_link = map_cell["links"][0] if map_cell["links"] else None
                dest_link = dest_cell["links"][0] if dest_cell["links"] else None
                conn.execute(
                    "INSERT INTO item_acquisition_treasuremap VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        category, item_id, label,
                        map_link["text"] if map_link else map_cell["text"],
                        map_link["item_id"] if map_link else None,
                        map_cell["text"],
                        dest_cell["text"],
                        dest_link["category"] if dest_link else None,
                        dest_link["item_id"] if dest_link else None,
                    ),
                )

        elif headers == ("목적지", "퀘스트"):
            bump("quest")
            for row in rows:
                sea_cell, quest_cell = row
                sea_link = sea_cell["links"][0] if sea_cell["links"] else None
                quest_links = [l for l in quest_cell["links"] if l["category"] == "quest"]
                city_links = [l for l in quest_cell["links"] if l["category"] == "city"]
                quest_link = quest_links[0] if quest_links else None
                city_link = city_links[-1] if city_links else None
                conn.execute(
                    "INSERT INTO item_acquisition_quest VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        category, item_id, label,
                        sea_cell["text"], sea_link["item_id"] if sea_link else None,
                        quest_link["text"] if quest_link else None,
                        quest_link["item_id"] if quest_link else None,
                        city_link["text"] if city_link else None,
                        city_link["item_id"] if city_link else None,
                        quest_cell["text"],
                    ),
                )

        elif headers == ("지역", "도시", "도시 인물"):
            bump("npc_location")
            for row in rows:
                region_cell, city_cell, npc_cell = row
                city_link = city_cell["links"][0] if city_cell["links"] else None
                npc_link = npc_cell["links"][0] if npc_cell["links"] else None
                conn.execute(
                    "INSERT INTO item_acquisition_npc_location VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        category, item_id, label, region_cell["text"],
                        city_cell["text"], city_link["item_id"] if city_link else None,
                        npc_cell["text"], npc_link["item_id"] if npc_link else None,
                        npc_link["category"] if npc_link else None,
                    ),
                )

        elif headers == ("아이템",):
            bump("from_item")
            for row in rows:
                (cell,) = row
                for src in split_multi_links(cell):
                    conn.execute(
                        "INSERT INTO item_acquisition_from_item VALUES (?,?,?,?,?,?)",
                        (category, item_id, label, src["name"], src["category"], src["item_id"]),
                    )

        elif headers == ("판매기간", "수량", "가격"):
            bump("directsale")
            for row in rows:
                period_cell, qty_cell, price_cell = row
                qty_m = re.search(r"\d+", qty_cell["text"])
                price_m = re.search(r"[\d,]+", price_cell["text"])
                conn.execute(
                    "INSERT INTO item_acquisition_directsale VALUES (?,?,?,?,?,?)",
                    (
                        category, item_id, label, period_cell["text"],
                        int(qty_m.group()) if qty_m else None,
                        int(price_m.group().replace(",", "")) if price_m else None,
                    ),
                )

        elif headers == ("종류", "내용"):
            bump("detail_list")
            for row in rows:
                type_cell, content_cell = row
                for c in split_multi_links_with_qty(content_cell):
                    conn.execute(
                        "INSERT INTO item_detail_list VALUES (?,?,?,?,?,?,?,?)",
                        (
                            category, item_id, label, type_cell["text"],
                            c["name"], c["category"], c["item_id"], c["qty"],
                        ),
                    )

        else:
            bump(f"UNMAPPED:{headers}")
            conn.execute(
                "INSERT INTO item_acquisition_unmapped VALUES (?,?,?,?,?)",
                (category, item_id, label, headers_json, rows_json),
            )

    conn.commit()
    print("[집계]")
    for shape, count in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {shape}: {count}")
    print(f"  (행 길이 불일치로 건너뛴 행: {malformed})")
    conn.close()


if __name__ == "__main__":
    materialize()
