#!/usr/bin/env python3
"""
dho_cache.sqlite3의 원본 HTML을 구조화된 dho_structured.sqlite3로 변환하는 스크립트

2단계 구성
---------
1. 범용 추출: 상세 페이지 HTML -> {title, attrs, tables} (카테고리 무관, 사이트 전체가
   "div.flex.gap-4 > label div + value div" 반복 구조를 쓰는 것을 확인함)
2. 스테이징 저장: raw_attrs / raw_tables 테이블에 그대로 적재 (재실행 시 원본 HTML을
   다시 파싱하지 않고 여기서부터 카테고리별 매핑을 이어갈 수 있음)

사용법
------
    python build_structured_db.py stage           # 전체 항목 범용 추출 -> 스테이징 적재
    python build_structured_db.py stage --limit 50 --category cannon
"""
import argparse
import json
import re
import sqlite3
from pathlib import Path

from bs4 import BeautifulSoup

CACHE_DB = Path(__file__).parent / "dho_cache.sqlite3"
STRUCT_DB = Path(__file__).parent / "dho_structured.sqlite3"
BASE_URL = "https://dho-archive.vercel.app"
LINK_RE = re.compile(r"^/db/([a-zA-Z]+)/(\d+)")


SCHEMA_VERSION = 3  # raw_attrs.images_json/position, raw_tables.position 추가 (v2 -> v3)


def init_structured_db(conn: sqlite3.Connection) -> None:
    """스키마가 바뀌면 SCHEMA_VERSION을 올리고, 이 함수가 감지해서 전체 재생성한다."""
    existing = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='items_core'"
    ).fetchone()
    if existing:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(items_core)").fetchall()}
        attr_cols = {r[1] for r in conn.execute("PRAGMA table_info(raw_attrs)").fetchall()}
        if "description" not in cols or "position" not in attr_cols:
            conn.executescript(
                "DROP TABLE IF EXISTS items_core; DROP TABLE IF EXISTS raw_attrs;"
                " DROP TABLE IF EXISTS raw_tables; DROP TABLE IF EXISTS staging_errors;"
            )
            conn.commit()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS items_core (
            category TEXT NOT NULL,
            item_id INTEGER NOT NULL,
            name TEXT,
            title TEXT,
            description TEXT,
            url TEXT,
            PRIMARY KEY (category, item_id)
        );

        CREATE TABLE IF NOT EXISTS raw_attrs (
            category TEXT NOT NULL,
            item_id INTEGER NOT NULL,
            label TEXT NOT NULL,
            text TEXT,
            links_json TEXT,
            images_json TEXT,
            position INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_raw_attrs_item
            ON raw_attrs (category, item_id);

        CREATE TABLE IF NOT EXISTS raw_tables (
            category TEXT NOT NULL,
            item_id INTEGER NOT NULL,
            label TEXT NOT NULL,
            headers_json TEXT NOT NULL,
            rows_json TEXT NOT NULL,
            position INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_raw_tables_item
            ON raw_tables (category, item_id);

        CREATE TABLE IF NOT EXISTS staging_errors (
            category TEXT NOT NULL,
            item_id INTEGER NOT NULL,
            reason TEXT
        );
        """
    )
    conn.commit()


def parse_cell(td) -> dict:
    # 셀 안에 중첩 <table>이 들어있는 경우(예: discovery "논전 콤보"/"장식품"의 발견물
    # 카드 목록, quest "필요"의 스킬 목록 — 여러 항목을 한 칸에 나열할 때 씀). 원본 소스가
    # 셀 사이에 공백 없이 붙어있어서 그냥 get_text()하면 "카르타고 유적한니발대리석상..."
    # 처럼 이어져버린다. 헤더/행 구조로 담을 수도 없으므로(우리 스키마는 셀 안에 표를 못
    # 담음), 중첩 표의 각 셀을 ", "로 이어붙인 인라인 텍스트로 펼쳐서 제자리에 넣는다.
    # 링크(<a>)는 그대로 옮겨서 아래 링크 추출 로직이 그대로 잡아내게 둔다.
    for nested_table in td.find_all("table"):
        inner_tds = [itd for itr in nested_table.find_all("tr") for itd in itr.find_all("td")]
        for i, itd in enumerate(inner_tds):
            if i > 0:
                nested_table.insert_before(", ")
            for child in list(itd.children):
                nested_table.insert_before(child.extract())
        nested_table.decompose()

    # <figure><img>+<figcaption> 형태(예: 퀘스트 "이미지" 행)를 먼저 뽑아내고 트리에서
    # 제거한다. 안 그러면 아래 get_text()가 figcaption 텍스트까지 주워서(예: "공략") 실제
    # 내용과 무관한 캡션 글자가 text 필드에 섞여 들어간다.
    images = []
    for fig in td.find_all("figure"):
        img = fig.find("img")
        if img and img.get("src"):
            caption_el = fig.find("figcaption")
            images.append(
                {
                    "src": img["src"],
                    "alt": img.get("alt", ""),
                    "caption": caption_el.get_text(strip=True) if caption_el else "",
                }
            )
        fig.decompose()
    for img in td.find_all("img"):
        if img.get("src"):
            images.append({"src": img["src"], "alt": img.get("alt", ""), "caption": ""})
        img.decompose()

    # get_text("\n", strip=True)는 인라인 링크/툴팁 경계마다 개별 텍스트 조각을 strip한 뒤
    # "\n"으로 이어붙여서 원본 공백("모험 | ", " ( 4 " 등)이 사라지고 표 셀이 줄바꿈투성이로
    # 깨졌었다. 원본 텍스트 노드는 이미 필요한 공백을 그대로 포함하고 있으므로 구분자 없이
    # 이어붙이기만 하면 원본 사이트와 동일하게 읽힌다.
    text = td.get_text().strip()
    links = []
    for a in td.find_all("a", href=True):
        m = LINK_RE.match(a["href"])
        if m:
            links.append(
                {"category": m.group(1), "item_id": int(m.group(2)), "text": a.get_text(strip=True)}
            )
    return {"text": text, "links": links, "images": images}


def extract_detail(html: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main")
    if main is None:
        return None
    h1 = main.find("h1")
    title = h1.get_text(strip=True) if h1 else None
    desc_p = main.select_one("section p.whitespace-pre-wrap")
    description = desc_p.get_text("\n", strip=True) if desc_p else None

    # attrs/tables는 각각 별도 리스트에 담기지만, 원본 페이지에서는 문서 순서대로 섞여서
    # 나온다(예: 퀘스트의 "필요"/"보상" 표가 "분류"/"난이도" 속성 사이에 낌). 렌더링 시
    # 원본과 같은 순서로 다시 합칠 수 있도록 각 항목에 순번(position)을 붙여둔다.
    attrs = []
    tables = []
    position = 0
    for row in main.select("div.flex.gap-4"):
        divs = row.find_all("div", recursive=False)
        if len(divs) < 2:
            continue
        label = divs[0].get_text(" ", strip=True)
        value_div = divs[1]
        table = value_div.find("table")
        if table:
            headers = [th.get_text(strip=True) for th in table.find_all("th")]
            rows = []
            # find_all(recursive=True, 기본값)로 tr/td를 찾으면 셀 안에 중첩된 표(예: discovery
            # "논전 콤보"의 발견물 카드 목록)의 tr/td까지 같이 딸려와서 열 개수가 안 맞거나
            # 중첩 표의 행이 바깥 표의 행인 것처럼 잘못 섞여 들어간다. tbody의 직계 tr, 그
            # tr의 직계 td만 골라서 중첩 표는 건드리지 않는다(중첩 표 내용 자체는 parse_cell이
            # 인라인 텍스트로 펼쳐서 담당).
            tbody = table.find("tbody") or table
            for tr in tbody.find_all("tr", recursive=False):
                cells = tr.find_all("td", recursive=False)
                if not cells:
                    continue
                rows.append([parse_cell(td) for td in cells])
            tables.append({"label": label, "headers": headers, "rows": rows, "position": position})
        else:
            cell = parse_cell(value_div)
            attrs.append(
                {
                    "label": label,
                    "text": cell["text"],
                    "links": cell["links"],
                    "images": cell["images"],
                    "position": position,
                }
            )
        position += 1

    return {"title": title, "description": description, "attrs": attrs, "tables": tables}


def stage_all(categories: list[str] | None, limit: int | None) -> None:
    cache_conn = sqlite3.connect(CACHE_DB)
    struct_conn = sqlite3.connect(STRUCT_DB)
    init_structured_db(struct_conn)

    query = "SELECT category, item_id, name FROM items"
    params: list = []
    if categories:
        placeholders = ",".join("?" * len(categories))
        query += f" WHERE category IN ({placeholders})"
        params.extend(categories)
    query += " ORDER BY category, item_id"
    if limit:
        query += " LIMIT ?"
        params.append(limit)

    items = cache_conn.execute(query, params).fetchall()
    print(f"[스테이징] 대상: {len(items)}건")

    done = 0
    errors = 0
    for category, item_id, name in items:
        url = f"{BASE_URL}/db/{category}/{item_id}"
        row = cache_conn.execute("SELECT html FROM pages WHERE url = ?", (url,)).fetchone()
        if not row:
            struct_conn.execute(
                "INSERT INTO staging_errors (category, item_id, reason) VALUES (?, ?, ?)",
                (category, item_id, "no cached html"),
            )
            errors += 1
            continue
        html = row[0]
        detail = extract_detail(html)
        if detail is None:
            struct_conn.execute(
                "INSERT INTO staging_errors (category, item_id, reason) VALUES (?, ?, ?)",
                (category, item_id, "no <main> found"),
            )
            errors += 1
            continue

        struct_conn.execute(
            """INSERT INTO items_core (category, item_id, name, title, description, url)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(category, item_id) DO UPDATE SET
                 name=excluded.name, title=excluded.title,
                 description=excluded.description, url=excluded.url""",
            (category, item_id, name, detail["title"], detail["description"], url),
        )
        struct_conn.execute(
            "DELETE FROM raw_attrs WHERE category = ? AND item_id = ?", (category, item_id)
        )
        struct_conn.execute(
            "DELETE FROM raw_tables WHERE category = ? AND item_id = ?", (category, item_id)
        )
        for attr in detail["attrs"]:
            struct_conn.execute(
                "INSERT INTO raw_attrs (category, item_id, label, text, links_json, images_json, position) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    category,
                    item_id,
                    attr["label"],
                    attr["text"],
                    json.dumps(attr["links"], ensure_ascii=False),
                    json.dumps(attr["images"], ensure_ascii=False),
                    attr["position"],
                ),
            )
        for table in detail["tables"]:
            struct_conn.execute(
                "INSERT INTO raw_tables (category, item_id, label, headers_json, rows_json, position) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    category,
                    item_id,
                    table["label"],
                    json.dumps(table["headers"], ensure_ascii=False),
                    json.dumps(table["rows"], ensure_ascii=False),
                    table["position"],
                ),
            )

        done += 1
        if done % 2000 == 0:
            struct_conn.commit()
            print(f"  진행: {done}/{len(items)}")

    struct_conn.commit()
    print(f"[스테이징] 완료: {done}건 성공, {errors}건 실패")
    struct_conn.close()
    cache_conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="DHO 구조화 DB 빌더")
    sub = parser.add_subparsers(dest="command", required=True)

    p_stage = sub.add_parser("stage", help="범용 추출 -> 스테이징 적재")
    p_stage.add_argument("--categories", type=str, help="쉼표로 구분된 카테고리 슬러그")
    p_stage.add_argument("--limit", type=int, default=None)

    args = parser.parse_args()

    if args.command == "stage":
        categories = [c.strip() for c in args.categories.split(",")] if args.categories else None
        stage_all(categories, args.limit)


if __name__ == "__main__":
    main()
