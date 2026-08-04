#!/usr/bin/env python3
"""
cannon/recipe/consumable/tarotCard처럼 손으로 다듬은 4개 카테고리를 제외한 나머지
카테고리를 자동으로 전용 테이블화하는 범용 스크립트.

방식
----
- 속성(raw_attrs)은 카테고리 테이블의 컬럼이 된다. 컬럼명은 원본 한글 라벨을 그대로 쓴다
  (번역 없이 site 용어를 그대로 유지 — 한국어 LLM이 질의할 때 오히려 자연스러움).
  값이 전부 숫자면 INTEGER, 아니면 TEXT로 자동 판별. 모든 항목에서 링크가 0~1개뿐인
  라벨은 "{라벨}_id"/"{라벨}_분류" 외래키 컬럼도 자동으로 추가한다.
- 표(raw_tables)는 헤더 모양이 build_acquisition.py가 이미 처리한 공유 패턴
  (COVERED_HEADER_SHAPES)이면 건너뛴다 (이미 공유 테이블에 있음).
  그 외의 표는 "{카테고리}__{라벨}" 관계 테이블로 만든다 (다중 헤더 모양이 섞여 있으면
  헤더 합집합으로 컬럼을 구성).

한계 (알고 있는 것, 나중에 필요한 카테고리만 골라서 손으로 개선 가능)
----
- 표 셀에 링크가 2개 이상이면 첫 번째 링크만 외래키로 잡고 전체 텍스트는 별도 보존한다.
- 원본 raw_attrs/raw_tables는 그대로 남아있으니 데이터 손실은 없다.
"""
import json
import os
import re
import sqlite3
from pathlib import Path

from build_acquisition import COVERED_HEADER_SHAPES

# DHO_DB_PATH로 오버라이드 가능 (dho_webapp.py/chat과 동일한 관례)
STRUCT_DB = Path(os.environ.get("DHO_DB_PATH", str(Path(__file__).parent / "dho_structured.sqlite3")))
ALREADY_HANDCRAFTED = {"cannon", "recipe", "consumable", "tarotCard"}
INT_RE = re.compile(r"-?\d+")
FULL_INT_RE = re.compile(r"-?\d+")


def q(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def build_category_table(conn: sqlite3.Connection, category: str) -> dict:
    table = category
    conn.execute(f"DROP TABLE IF EXISTS {q(table)}")

    labels = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT label FROM raw_attrs WHERE category = ? ORDER BY label", (category,)
        )
    ]

    col_defs = ["item_id INTEGER PRIMARY KEY", "name TEXT", "description TEXT"]
    label_meta = {}
    for label in labels:
        rows = conn.execute(
            "SELECT item_id, text, links_json FROM raw_attrs WHERE category = ? AND label = ?",
            (category, label),
        ).fetchall()
        texts = [t for _, t, _ in rows if t]
        all_int = bool(texts) and all(FULL_INT_RE.fullmatch(t.strip()) for t in texts)
        link_counts = [len(json.loads(lj)) for _, _, lj in rows]
        has_fk = any(c == 1 for c in link_counts) and all(c <= 1 for c in link_counts)

        col_type = "INTEGER" if all_int else "TEXT"
        col_defs.append(f"{q(label)} {col_type}")
        if has_fk:
            col_defs.append(f"{q(label + '_id')} INTEGER")
            col_defs.append(f"{q(label + '_분류')} TEXT")
        label_meta[label] = {"all_int": all_int, "has_fk": has_fk}

    conn.execute(f"CREATE TABLE {q(table)} ({', '.join(col_defs)})")

    item_rows = conn.execute(
        "SELECT item_id, name, description FROM items_core WHERE category = ?", (category,)
    ).fetchall()

    attr_by_item: dict[int, dict[str, tuple]] = {}
    for label in labels:
        for item_id, text, links_json in conn.execute(
            "SELECT item_id, text, links_json FROM raw_attrs WHERE category = ? AND label = ?",
            (category, label),
        ):
            attr_by_item.setdefault(item_id, {})[label] = (text, json.loads(links_json))

    col_names = ["item_id", "name", "description"] + [
        c for label in labels for c in ([label, label + "_id", label + "_분류"] if label_meta[label]["has_fk"] else [label])
    ]
    placeholders = ",".join("?" * len(col_names))
    insert_sql = f"INSERT INTO {q(table)} ({','.join(q(c) for c in col_names)}) VALUES ({placeholders})"

    for item_id, name, description in item_rows:
        values = [item_id, name, description]
        attrs = attr_by_item.get(item_id, {})
        for label in labels:
            text, links = attrs.get(label, (None, []))
            meta = label_meta[label]
            if meta["all_int"] and text:
                m = INT_RE.search(text)
                values.append(int(m.group()) if m else None)
            else:
                values.append(text)
            if meta["has_fk"]:
                link = links[0] if links else None
                values.append(link["item_id"] if link else None)
                values.append(link["category"] if link else None)
        conn.execute(insert_sql, values)

    return {"labels": labels}


def build_relation_tables(conn: sqlite3.Connection, category: str) -> dict:
    stats = {}
    label_rows: dict[str, list] = {}
    for item_id, label, headers_json, rows_json in conn.execute(
        "SELECT item_id, label, headers_json, rows_json FROM raw_tables WHERE category = ?", (category,)
    ):
        headers = tuple(json.loads(headers_json))
        if headers in COVERED_HEADER_SHAPES:
            continue
        rows = json.loads(rows_json)
        label_rows.setdefault(label, []).append((item_id, headers, rows))

    for label, entries in label_rows.items():
        union_headers = []
        for _, headers, _ in entries:
            for h in headers:
                if h not in union_headers:
                    union_headers.append(h)

        table = f"{category}__{label}"
        conn.execute(f"DROP TABLE IF EXISTS {q(table)}")
        col_defs = ["item_id INTEGER", "row_index INTEGER"]
        for h in union_headers:
            col_defs.append(f"{q(h + '_text')} TEXT")
            col_defs.append(f"{q(h + '_id')} INTEGER")
            col_defs.append(f"{q(h + '_분류')} TEXT")
        conn.execute(f"CREATE TABLE {q(table)} ({', '.join(col_defs)})")

        col_names = ["item_id", "row_index"] + [
            c for h in union_headers for c in (h + "_text", h + "_id", h + "_분류")
        ]
        placeholders = ",".join("?" * len(col_names))
        insert_sql = f"INSERT INTO {q(table)} ({','.join(q(c) for c in col_names)}) VALUES ({placeholders})"

        n = 0
        for item_id, headers, rows in entries:
            for row_index, row in enumerate(rows):
                if len(row) != len(headers):
                    continue
                cell_by_header = dict(zip(headers, row))
                values = [item_id, row_index]
                for h in union_headers:
                    cell = cell_by_header.get(h)
                    if cell is None:
                        values.extend([None, None, None])
                        continue
                    link = cell["links"][0] if cell["links"] else None
                    values.append(cell["text"])
                    values.append(link["item_id"] if link else None)
                    values.append(link["category"] if link else None)
                conn.execute(insert_sql, values)
                n += 1
        stats[label] = n

    return stats


def materialize() -> None:
    conn = sqlite3.connect(STRUCT_DB)
    categories = [
        r[0]
        for r in conn.execute("SELECT DISTINCT category FROM items_core ORDER BY category")
        if r[0] not in ALREADY_HANDCRAFTED
    ]
    print(f"[generic] 대상 카테고리: {len(categories)}개")

    for category in categories:
        meta = build_category_table(conn, category)
        rel_stats = build_relation_tables(conn, category)
        n = conn.execute(f"SELECT COUNT(*) FROM {q(category)}").fetchone()[0]
        conn.commit()
        print(f"  {category}: {n}건, 속성 {len(meta['labels'])}개, 관계표 {rel_stats}")

    conn.close()
    print("[generic] 완료")


if __name__ == "__main__":
    materialize()
