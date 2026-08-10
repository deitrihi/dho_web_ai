#!/usr/bin/env python3
"""
PostgreSQL(구조화 데이터가 이관된 서빙 DB)에 담긴 데이터를 원본 사이트와 동일한 정보
구조로 보여주는 조회용 웹앱

범위: 카테고리 목록 -> 카테고리별 항목 목록 -> 항목 상세(속성 + 표) 3단 구조.
items_core/raw_attrs/raw_tables는 원본 페이지를 1:1로 그대로 옮겨온 것이라
(scrape_hidden_tabs.py로 보강된 숨은 탭 데이터까지 포함) 이 세 테이블만으로
원본과 동일한 정보를 보여줄 수 있다. 디자인은 원본 CSS를 따라하지 않고 간결하게 새로 작성.

사용법
------
    python dho_webapp.py                # http://localhost:5050 에서 실행 (DATABASE_URL 필요)
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from flask import Flask, g, render_template, request, abort, url_for, redirect
from markupsafe import Markup, escape

_NUMERIC_RE = re.compile(r"^-?[\d,]+$")


def _q(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


DATABASE_URL = os.environ["DATABASE_URL"]
PER_PAGE = 100

# chat/ 챗봇의 실제 접속 주소. 외부에서는 도메인 443 하나로만 들어오고, nginx가 그 안에서
# "/"는 webapp:5050으로, "/chat"은 chat:3000으로 나눠서 프록시해준다 — 즉 브라우저 입장에서
# webapp과 chat은 이미 같은 origin(도메인+443)에 있으므로, 기본값은 상대경로 "/chat"이면
# nginx가 알아서 chat 컨테이너로 넘겨준다(포트를 브라우저가 알 필요 없음).
# nginx 없이 webapp을 직접 접속해서 테스트할 때만(로컬 python dho_webapp.py, 또는 NAS를
# IP:5050으로 직접 접속) 상대경로가 webapp 자신의 포트로 풀려버려 안 통하므로, 그럴 때만
# DHO_CHAT_URL=http://<host>:3000/chat 처럼 절대경로로 오버라이드해서 확인한다.
CHAT_URL = os.environ.get("DHO_CHAT_URL", "/chat")

app = Flask(__name__)
# {% %} 블록 태그 주변 개행/들여쓰기를 렌더링 결과에 안 남기게 함. 안 그러면 표 셀/속성값에
# white-space:pre-wrap을 쓸 때(원본 텍스트의 의도된 줄바꿈을 보존하려고) 템플릿 자체의
# 들여쓰기 공백까지 같이 렌더링되어 버린다(예: .links가 <td>의 pre-wrap을 물려받아 링크마다
# 줄바꿈되던 문제, .row-value에 pre-wrap 추가 후 속성 행마다 빈 줄이 생기던 문제).
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True


def render_text_with_links(text: str | None, links: list[dict]) -> Markup:
    """text 안에서 링크에 해당하는 부분을 실제 <a> 태그로 치환해서 렌더링한다.
    text는 셀 전체를 get_text()한 결과라 링크의 표시 텍스트를 이미 포함하고 있는데,
    거기에 text와 links를 나란히 렌더링하면 같은 내용이 줄만 바뀌어 중복 표시된다."""
    text = text or ""
    pieces: list[Markup] = []
    unmatched: list[dict] = []
    pos = 0
    for link in links or []:
        label = link.get("text") or ""
        if not label:
            continue
        idx = text.find(label, pos)
        if idx == -1:
            unmatched.append(link)
            continue
        if idx > pos:
            pieces.append(escape(text[pos:idx]))
        href = url_for("item_detail", category=link["category"], item_id=link["item_id"])
        pieces.append(Markup("<a href=\"{}\">{}</a>").format(href, label))
        pos = idx + len(label)
    if pos < len(text):
        pieces.append(escape(text[pos:]))
    result = Markup("").join(pieces)
    for link in unmatched:  # 본문에서 못 찾은 링크(공백 차이 등, 드묾)는 잃지 않게 뒤에 붙임
        href = url_for("item_detail", category=link["category"], item_id=link["item_id"])
        result += Markup(" <a href=\"{}\">{}</a>").format(href, link.get("text") or "")
    return result


app.jinja_env.filters["with_links"] = render_text_with_links


def get_db() -> psycopg.Connection:
    if "db" not in g:
        g.db = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def get_write_db() -> psycopg.Connection:
    """조회용 get_db()와 별개로, 쓰기가 필요한 요청(새 항목/수정)에서만 연다.
    next_item_id()가 결과를 위치 인덱스(row[0])로 읽으므로 dict_row를 안 쓴다."""
    return psycopg.connect(DATABASE_URL)


# item_backlinks/item_acquisition_*/item_transmutation_*/item_detail_list/카테고리 전용
# 테이블(cannon 등 211개)은 전부 raw_attrs/raw_tables에서 파생되는 데이터라, webapp이 그
# 두 테이블에 쓸 때(_save_item)마다 다시 만들어주지 않으면 chat이 webapp에서 추가/수정한
# 항목을 못 본다. 순서: backlinks/acquisition(공유 관계 테이블) -> 카테고리 전용 테이블.
DERIVED_PIPELINE_SCRIPTS = [
    "build_backlinks.py",
    "build_acquisition.py",
    "materialize_generic.py",
    "materialize_cannon.py",
    "materialize_recipe.py",
    "materialize_consumable.py",
    "materialize_tarotcard.py",
    "build_search_index.py",
]
PROJECT_ROOT = Path(__file__).parent


def rebuild_derived_tables() -> list[str]:
    """전체 33,496+건 기준 로컬 측정 약 12초(스크립트 7개 합계) — 증분 갱신보다 훨씬
    단순하고, 항목 저장이 빈번한 작업이 아니라 저장 요청마다 동기로 기다려도 감당 가능하다고
    판단해서 전체 재생성 방식을 선택했다. 실패해도 항목 저장 자체는 이미 끝난 뒤라 롤백하지
    않고, 실패한 스크립트 이름과 stderr만 모아서 반환한다(호출부에서 로그로 남김)."""
    errors = []
    # PYTHONUTF8=1: 자식 스크립트의 한글 print() 출력이 콘솔 코드페이지(Windows에서는 cp949 등)
    # 대신 항상 UTF-8로 나가게 강제 — 안 하면 부모가 UTF-8로 디코드할 때 깨진 바이트로
    # UnicodeDecodeError가 남(플랫폼별 로케일에 따라 달라지는 문제라 명시적으로 고정해야 함).
    # DATABASE_URL은 이미 os.environ에 있으므로 별도로 주입할 필요 없다.
    env = {**os.environ, "PYTHONUTF8": "1"}
    for script in DERIVED_PIPELINE_SCRIPTS:
        try:
            result = subprocess.run(
                [sys.executable, str(PROJECT_ROOT / script)],
                cwd=PROJECT_ROOT,
                env=env,
                capture_output=True,
                encoding="utf-8",
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            errors.append(f"{script}: 120초 초과로 중단됨")
            continue
        if result.returncode != 0:
            errors.append(f"{script}: {result.stderr.strip()[-500:]}")
    return errors


NEW_ITEM_ID_BASE = 900_000_000  # 나중에 원본 사이트를 재크롤링해도 item_id가 안 겹치도록
# 사용자가 직접 추가한 항목은 이 범위부터 순번을 매긴다 (원본 item_id는 대체로 수백만 이하)


def next_item_id(db: psycopg.Connection, category: str) -> int:
    row = db.execute(
        "SELECT MAX(item_id) FROM items_core WHERE category = %s AND item_id >= %s",
        (category, NEW_ITEM_ID_BASE),
    ).fetchone()
    return (row[0] or NEW_ITEM_ID_BASE - 1) + 1


def _parse_attrs_form(form) -> list[dict]:
    labels = form.getlist("attr_label")
    texts = form.getlist("attr_text")
    attrs = []
    for i, (label, text) in enumerate(zip(labels, texts)):
        label = label.strip()
        if not label:
            continue
        attrs.append({"label": label, "text": text.strip(), "position": i})
    return attrs


def _parse_tables_form(form) -> list[dict]:
    """표 입력은 탭으로 구분된 텍스트(엑셀에서 복붙 가능)를 받아서 첫 줄을 헤더로 파싱한다."""
    labels = form.getlist("table_label")
    grids = form.getlist("table_grid")
    tables = []
    position_base = 1000  # 속성(0..N) 뒤에 표가 오도록 큰 값에서 시작
    for i, (label, grid) in enumerate(zip(labels, grids)):
        label = label.strip()
        lines = [ln for ln in grid.splitlines() if ln.strip() != ""]
        if not label or not lines:
            continue
        headers = [c.strip() for c in lines[0].split("\t")]
        rows = []
        for ln in lines[1:]:
            cells = [c.strip() for c in ln.split("\t")]
            cells += [""] * (len(headers) - len(cells))
            rows.append([{"text": c, "links": [], "images": []} for c in cells[: len(headers)]])
        tables.append({"label": label, "headers": headers, "rows": rows, "position": position_base + i})
    return tables


def _save_item(
    db: psycopg.Connection,
    category: str,
    item_id: int,
    name: str,
    title: str,
    description: str | None,
    attrs: list[dict],
    tables: list[dict],
) -> None:
    db.execute(
        "INSERT INTO items_core (category, item_id, name, title, description, url) "
        "VALUES (%s, %s, %s, %s, %s, NULL) "
        "ON CONFLICT (category, item_id) DO UPDATE SET "
        "name=excluded.name, title=excluded.title, description=excluded.description",
        (category, item_id, name, title, description),
    )
    db.execute("DELETE FROM raw_attrs WHERE category = %s AND item_id = %s", (category, item_id))
    db.execute("DELETE FROM raw_tables WHERE category = %s AND item_id = %s", (category, item_id))
    for attr in attrs:
        db.execute(
            "INSERT INTO raw_attrs (category, item_id, label, text, links_json, images_json, position) "
            "VALUES (%s, %s, %s, %s, '[]', '[]', %s)",
            (category, item_id, attr["label"], attr["text"], attr["position"]),
        )
    for table in tables:
        db.execute(
            "INSERT INTO raw_tables (category, item_id, label, headers_json, rows_json, position) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (
                category,
                item_id,
                table["label"],
                json.dumps(table["headers"], ensure_ascii=False),
                json.dumps(table["rows"], ensure_ascii=False),
                table["position"],
            ),
        )
    db.commit()


def get_category_label(db: psycopg.Connection, slug: str) -> str:
    row = db.execute(
        "SELECT label_ko FROM category_localization WHERE slug = %s", (slug,)
    ).fetchone()
    return row["label_ko"] if row else slug


def get_group_title(db: psycopg.Connection, slug: str) -> str | None:
    row = db.execute(
        "SELECT group_title_ko FROM category_localization WHERE slug = %s", (slug,)
    ).fetchone()
    return row["group_title_ko"] if row else None


def get_nav_groups(db: psycopg.Connection) -> list[dict]:
    rows = db.execute(
        """
        SELECT ic.category AS slug, COUNT(*) AS cnt,
               cl.label_ko, cl.group_title_ko, cl.group_order, cl.order_in_group
        FROM items_core ic
        LEFT JOIN category_localization cl ON cl.slug = ic.category
        GROUP BY ic.category, cl.label_ko, cl.group_title_ko, cl.group_order, cl.order_in_group
        ORDER BY COALESCE(cl.group_order, 999), COALESCE(cl.order_in_group, 999), ic.category
        """
    ).fetchall()

    groups: list[dict] = []
    groups_by_title: dict[str, dict] = {}
    for r in rows:
        title = r["group_title_ko"] or "기타"
        if title not in groups_by_title:
            g_entry = {"title": title, "categories": []}
            groups_by_title[title] = g_entry
            groups.append(g_entry)
        groups_by_title[title]["categories"].append(
            {"slug": r["slug"], "label": r["label_ko"] or r["slug"], "cnt": r["cnt"]}
        )
    return groups


@app.context_processor
def inject_nav_groups():
    return {"nav_groups": get_nav_groups(get_db())}


@app.route("/")
def index():
    db = get_db()
    return render_template("index.html", groups=get_nav_groups(db))


@app.route("/assistant")
def chat_ai():
    # "/chat"으로 시작하는 경로는 절대 쓰면 안 됨 — nginx의 `location /chat`은 접두어
    # 매칭이라 "/chat-ai" 같은 경로도 그 규칙에 걸려서 chat 컨테이너(3000)로 넘어가 버리고,
    # 거긴 그런 라우트가 없어서 404가 남(webapp까지 요청이 오지도 못함). 그래서 wrapper
    # 페이지는 "chat"과 무관한 "/assistant"에 두고, 안의 iframe만 CHAT_URL("/chat")을
    # 가리키게 한다.
    return render_template("chat.html", chat_url=CHAT_URL)


LIST_MAX_COLS = 7
LIST_MAX_AVG_LEN = 20  # 이보다 평균 글자 수가 긴 속성(예: 퀘스트 "진행" 같은 장문)은
# 목록 표의 컬럼으로 안 씀 — 원본 사이트가 카테고리마다 수작업으로 고른 "핵심 스탯"
# 컬럼(장비품: 분류/내구/공격/방어 등)을 흉내내되, 70개 카테고리를 전부 수작업으로
# 고르는 대신 "짧고 분류값스러운 속성일수록 목록에 어울린다"는 휴리스틱으로 자동 선정


def get_list_columns(db: psycopg.Connection, category: str) -> list[dict]:
    rows = db.execute(
        "SELECT label, AVG(LENGTH(text)) AS avg_len, MIN(position) AS pos "
        "FROM raw_attrs WHERE category = %s AND text IS NOT NULL AND text != '' AND label != '이미지' "
        "GROUP BY label ORDER BY pos, label",
        (category,),
    ).fetchall()

    columns = []
    for r in rows:
        if r["avg_len"] is None or r["avg_len"] > LIST_MAX_AVG_LEN:
            continue
        texts = [
            t["text"]
            for t in db.execute(
                "SELECT DISTINCT text FROM raw_attrs WHERE category = %s AND label = %s "
                "AND text IS NOT NULL AND text != ''",
                (category, r["label"]),
            ).fetchall()
        ]
        numeric = bool(texts) and all(_NUMERIC_RE.match(t) for t in texts)
        columns.append({"label": r["label"], "numeric": numeric})
        if len(columns) >= LIST_MAX_COLS:
            break
    return columns


@app.route("/<category>")
def category_list(category):
    db = get_db()
    total = db.execute(
        "SELECT COUNT(*) AS total FROM items_core WHERE category = %s", (category,)
    ).fetchone()["total"]
    if total == 0:
        abort(404)

    columns = get_list_columns(db, category)
    col_labels = [c["label"] for c in columns]

    sort = request.args.get("sort", "item_id")
    direction = "desc" if request.args.get("dir") == "desc" else "asc"
    if sort not in ({"item_id", "name"} | set(col_labels)):
        sort = "item_id"

    page = max(1, request.args.get("page", 1, type=int))
    offset = (page - 1) * PER_PAGE

    if columns:
        pivot_sql = ", ".join(
            f"MAX(CASE WHEN ra.label = %s THEN ra.text END) AS {_q(c['label'])}" for c in columns
        )
        order_col = "ic.item_id" if sort == "item_id" else "ic.name" if sort == "name" else _q(sort)
        numeric_col = next((c for c in columns if c["label"] == sort and c["numeric"]), None)
        if numeric_col:
            order_col = f"CAST(REPLACE({_q(sort)}, ',', '') AS INTEGER)"
        sql = (
            f"SELECT ic.item_id, ic.name, ic.title, {pivot_sql} FROM items_core ic "
            "LEFT JOIN raw_attrs ra ON ra.category = ic.category AND ra.item_id = ic.item_id "
            "WHERE ic.category = %s GROUP BY ic.item_id, ic.name, ic.title "
            f"ORDER BY {order_col} {direction.upper()}, ic.item_id ASC LIMIT %s OFFSET %s"
        )
        params = col_labels + [category, PER_PAGE, offset]
    else:
        order_col = "name" if sort == "name" else "item_id"
        sql = (
            "SELECT item_id, name, title FROM items_core WHERE category = %s "
            f"ORDER BY {order_col} {direction.upper()} LIMIT %s OFFSET %s"
        )
        params = [category, PER_PAGE, offset]

    items = db.execute(sql, params).fetchall()
    total_pages = (total + PER_PAGE - 1) // PER_PAGE
    return render_template(
        "category.html",
        category=category,
        category_label=get_category_label(db, category),
        group_title=get_group_title(db, category),
        columns=columns,
        items=items,
        sort=sort,
        dir=direction,
        page=page,
        total_pages=total_pages,
        total=total,
    )


def _parse_links(links_json: str | None) -> list[dict]:
    return json.loads(links_json) if links_json else []


BACKLINKS_PER_CATEGORY = 30


def get_backlinks(db: psycopg.Connection, category: str, item_id: int) -> dict:
    """이 항목을 참조하는 다른 항목들을 소스 카테고리별로 묶어서 반환한다.
    일부 항목(흔한 스킬/재료 등)은 backlink가 수천 건이라 카테고리당
    BACKLINKS_PER_CATEGORY개까지만 보여주고 나머지는 개수만 표시한다."""
    counts = db.execute(
        "SELECT source_category, COUNT(*) AS cnt FROM item_backlinks "
        "WHERE target_category = %s AND target_item_id = %s "
        "GROUP BY source_category ORDER BY cnt DESC",
        (category, item_id),
    ).fetchall()
    if not counts:
        return {"groups": [], "total": 0}

    groups = []
    total = 0
    for c in counts:
        src_cat = c["source_category"]
        cnt = c["cnt"]
        total += cnt
        items = db.execute(
            "SELECT b.source_item_id, ic.name, ic.title, b.source_label FROM item_backlinks b "
            "JOIN items_core ic ON ic.category = b.source_category AND ic.item_id = b.source_item_id "
            "WHERE b.target_category = %s AND b.target_item_id = %s AND b.source_category = %s "
            "ORDER BY b.source_item_id LIMIT %s",
            (category, item_id, src_cat, BACKLINKS_PER_CATEGORY),
        ).fetchall()
        groups.append(
            {
                "category": src_cat,
                "category_label": get_category_label(db, src_cat),
                "count": cnt,
                # "items"라는 키 이름은 쓰지 않는다 — Jinja에서 dict.items()를 dict의
                # 내장 메서드로 먼저 찾아버려서 템플릿의 {% for it in g.items %}가
                # 우리가 넣은 리스트가 아니라 파이썬 builtin 메서드를 순회하려다 깨진다.
                "entries": [
                    {
                        "item_id": it["source_item_id"],
                        "name": it["name"] or it["title"] or it["source_item_id"],
                        "label": it["source_label"],
                    }
                    for it in items
                ],
                "more": cnt - len(items),
            }
        )
    return {"groups": groups, "total": total}


@app.route("/<category>/<int:item_id>")
def item_detail(category, item_id):
    db = get_db()
    item = db.execute(
        "SELECT category, item_id, name, title, description FROM items_core "
        "WHERE category = %s AND item_id = %s",
        (category, item_id),
    ).fetchone()
    if item is None:
        abort(404)

    # attrs/tables를 원본 문서 순서(position)대로 하나의 리스트로 합쳐서 렌더링한다.
    # (예전엔 속성 전부 -> 표 전부 순으로 따로 렌더링해서, 원본에서는 "필요"/"보상" 표가
    # "분류"/"난이도" 바로 다음에 나오는데 여기선 맨 아래로 밀려나는 문제가 있었음)
    rows: list[dict] = []

    for row in db.execute(
        "SELECT label, text, links_json, images_json, position FROM raw_attrs "
        "WHERE category = %s AND item_id = %s ORDER BY position, insert_seq",
        (category, item_id),
    ):
        rows.append(
            {
                "type": "attr",
                "position": row["position"],
                "label": row["label"],
                "text": row["text"],
                "links": _parse_links(row["links_json"]),
                "images": json.loads(row["images_json"]) if row["images_json"] else [],
            }
        )

    table_rows = db.execute(
        "SELECT label, headers_json, rows_json, position FROM raw_tables "
        "WHERE category = %s AND item_id = %s ORDER BY position, insert_seq",
        (category, item_id),
    ).fetchall()

    # 같은 label이 여러 표로 나올 수 있음(예: 획득 방법이 퀘스트/해상 NPC 등으로 나뉨) ->
    # 첫 헤더로 구분되는 이름을 붙여서 헤딩만 봐도 어떤 표인지 알 수 있게 함
    label_counts: dict[str, int] = {}
    for tr in table_rows:
        label_counts[tr["label"]] = label_counts.get(tr["label"], 0) + 1
    for tr in table_rows:
        headers = json.loads(tr["headers_json"])
        heading = tr["label"]
        if label_counts[tr["label"]] > 1 and headers:
            heading = f"{tr['label']} — {headers[0]}"
        rows.append(
            {
                "type": "table",
                "position": tr["position"],
                "heading": heading,
                "headers": headers,
                "rows": json.loads(tr["rows_json"]),
            }
        )

    rows.sort(key=lambda r: r["position"])

    return render_template(
        "item.html",
        item=item,
        category=category,
        category_label=get_category_label(db, category),
        group_title=get_group_title(db, category),
        rows=rows,
        backlinks=get_backlinks(db, category, item_id),
    )


@app.route("/<category>/new", methods=["GET", "POST"])
def item_new(category):
    db = get_db()
    if not db.execute("SELECT 1 FROM items_core WHERE category = %s LIMIT 1", (category,)).fetchone():
        abort(404)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            abort(400)
        title = request.form.get("title", "").strip() or name
        description = request.form.get("description", "").strip() or None
        attrs = _parse_attrs_form(request.form)
        tables = _parse_tables_form(request.form)

        wdb = get_write_db()
        try:
            item_id = next_item_id(wdb, category)
            _save_item(wdb, category, item_id, name, title, description, attrs, tables)
        finally:
            wdb.close()
        rebuild_errors = rebuild_derived_tables()
        for err in rebuild_errors:
            app.logger.error("파생 테이블 재생성 실패: %s", err)
        return redirect(url_for("item_detail", category=category, item_id=item_id))

    return render_template(
        "item_form.html",
        mode="new",
        category=category,
        category_label=get_category_label(db, category),
        group_title=get_group_title(db, category),
        item=None,
        attrs=[],
        tables=[],
    )


@app.route("/<category>/<int:item_id>/edit", methods=["GET", "POST"])
def item_edit(category, item_id):
    db = get_db()
    item = db.execute(
        "SELECT category, item_id, name, title, description FROM items_core "
        "WHERE category = %s AND item_id = %s",
        (category, item_id),
    ).fetchone()
    if item is None:
        abort(404)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            abort(400)
        title = request.form.get("title", "").strip() or name
        description = request.form.get("description", "").strip() or None
        attrs = _parse_attrs_form(request.form)
        tables = _parse_tables_form(request.form)

        wdb = get_write_db()
        try:
            _save_item(wdb, category, item_id, name, title, description, attrs, tables)
        finally:
            wdb.close()
        rebuild_errors = rebuild_derived_tables()
        for err in rebuild_errors:
            app.logger.error("파생 테이블 재생성 실패: %s", err)
        return redirect(url_for("item_detail", category=category, item_id=item_id))

    attrs = [
        {"label": r["label"], "text": r["text"] or ""}
        for r in db.execute(
            "SELECT label, text FROM raw_attrs WHERE category = %s AND item_id = %s ORDER BY position, insert_seq",
            (category, item_id),
        )
    ]
    tables = []
    for r in db.execute(
        "SELECT label, headers_json, rows_json FROM raw_tables WHERE category = %s AND item_id = %s "
        "ORDER BY position, insert_seq",
        (category, item_id),
    ):
        headers = json.loads(r["headers_json"])
        grid_lines = ["\t".join(headers)]
        for row in json.loads(r["rows_json"]):
            grid_lines.append("\t".join(cell.get("text", "") for cell in row))
        tables.append({"label": r["label"], "grid": "\n".join(grid_lines)})

    return render_template(
        "item_form.html",
        mode="edit",
        category=category,
        category_label=get_category_label(db, category),
        group_title=get_group_title(db, category),
        item=item,
        attrs=attrs,
        tables=tables,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)
