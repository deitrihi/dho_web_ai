#!/usr/bin/env python3
"""DHO 구조화 데이터(items_core/raw_attrs/raw_tables)를 Markdown으로 변환해서
Wiki.js GraphQL API로 페이지를 생성/갱신하는 스크립트.

dho_webapp.py의 item_detail()과 같은 방식(attrs+tables를 position 순으로 병합,
raw_attrs.links_json을 text 안에서 찾아 링크로 치환)으로 콘텐츠를 만들지만, 출력이
HTML이 아니라 Markdown이고 링크는 위키 경로(/dho/<category>/<item_id>)를 가리킨다.

페이지 경로: dho/<category>/<item_id>  (예: dho/tarotCard/8611)
콘텐츠 해시(raw_attrs+raw_tables 기반)가 이전과 같으면 update를 건너뛴다 —
Wiki.js pageHistory가 매 실행마다 쌓이는 것을 방지.

사용법
------
    python build_wikijs_pages.py --categories tarotCard          # 파일럿(카테고리 지정)
    python build_wikijs_pages.py --all                           # 전체 70개 카테고리
    python build_wikijs_pages.py --all --concurrency 16           # 동시 요청 수 조절(기본 8)
    (DATABASE_URL, WIKIJS_URL, WIKI_ADMIN_EMAIL, WIKI_ADMIN_PASS 환경변수 필요)

동시성: 카테고리 안 항목들을 스레드풀로 병렬 처리하되, Wiki.js에 실제로 쓰는(create/update)
호출만은 전역 락으로 직렬화한다. 처음엔 쓰기까지 전부 병렬로 돌렸는데, Wiki.js 2.5.314가
페이지 생성 시 내부적으로 도는 "rebuild-tree" 작업이 동시 요청을 못 견디고
`pageTree_pkey`/`pagetree_parent_foreign` 위반으로 실패하는 걸 실측으로 확인함(카테고리당
수십 건씩 실패). 따라서 마크다운 생성(DB 조회, CPU 작업)은 병렬로 겹치게 하고, 실제
Wiki.js 쓰기 요청만 한 번에 하나씩 나가도록 직렬화해서 안정성을 우선한다 — 순수 동시
쓰기만큼의 배속은 못 내지만, 다음 항목의 DB 조회/마크다운 생성이 현재 쓰기 대기 중에
겹쳐 처리되는 만큼은 이득이 있다.
"""
import argparse
import hashlib
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import psycopg
import requests
from psycopg.rows import dict_row

# Windows 콘솔 기본 코드페이지(cp949)는 em dash(—) 등 일부 문자를 인코딩 못 해서 print()가
# UnicodeEncodeError로 죽는 문제가 있었음 — stdout/stderr를 UTF-8로 강제 전환해서 방지.
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

DATABASE_URL = os.environ["DATABASE_URL"]
WIKIJS_URL = os.environ.get("WIKIJS_URL", "http://localhost:3001")
WIKI_ADMIN_EMAIL = os.environ["WIKI_ADMIN_EMAIL"]
WIKI_ADMIN_PASS = os.environ["WIKI_ADMIN_PASS"]
GRAPHQL_ENDPOINT = f"{WIKIJS_URL}/graphql"

JWT_REFRESH_SECONDS = 20 * 60  # 토큰 만료(30분, server/setup.js 기본값)보다 여유 있게 재로그인
# 33,496건 전체 백필 실측 결과, Wiki.js에 쌓인 페이지 수가 늘어날수록(검색 인덱싱/페이지트리
# 갱신 부담 증가로) 저장 요청이 느려져서 뒷부분 카테고리에서 기본 30초 타임아웃에 걸리는
# 사례가 늘었음(예: skill 487건 중 322건). 실패 항목 재시도 시엔
# WIKIJS_REQUEST_TIMEOUT=90 처럼 늘려서 돌리는 걸 권장.
REQUEST_TIMEOUT = int(os.environ.get("WIKIJS_REQUEST_TIMEOUT", "30"))

_thread_local = threading.local()
_write_lock = threading.Lock()
WRITE_MAX_RETRIES = 3


def get_conn() -> psycopg.Connection:
    """스레드마다 자신만의 DB 커넥션을 연다(psycopg.Connection은 스레드 세이프하지 않음)."""
    conn = getattr(_thread_local, "conn", None)
    if conn is None:
        conn = psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=False)
        _thread_local.conn = conn
    return conn


class WikiClient:
    def __init__(self):
        self._jwt = None
        self._jwt_at = 0.0
        self._lock = threading.Lock()

    def _login_locked(self) -> None:
        r = requests.post(
            GRAPHQL_ENDPOINT,
            json={
                "query": (
                    'mutation($u:String!,$p:String!){ authentication { '
                    'login(username:$u, password:$p, strategy:"local") { '
                    "responseResult { succeeded message } jwt } } }"
                ),
                "variables": {"u": WIKI_ADMIN_EMAIL, "p": WIKI_ADMIN_PASS},
            },
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        login = r.json()["data"]["authentication"]["login"]
        if not login["responseResult"]["succeeded"]:
            raise RuntimeError(f"Wiki.js 로그인 실패: {login['responseResult']['message']}")
        self._jwt = login["jwt"]
        self._jwt_at = time.time()

    def _token(self) -> str:
        with self._lock:
            if self._jwt is None or time.time() - self._jwt_at > JWT_REFRESH_SECONDS:
                self._login_locked()
            return self._jwt

    def gql(self, query: str, variables: dict | None = None, allow_errors: bool = False) -> dict:
        r = requests.post(
            GRAPHQL_ENDPOINT,
            json={"query": query, "variables": variables or {}},
            headers={"Authorization": f"Bearer {self._token()}"},
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        if "errors" in data and not allow_errors:
            raise RuntimeError(f"GraphQL 오류: {data['errors']}")
        return data


SINGLE_BY_PATH = (
    'query($path:String!,$locale:String!){ pages { singleByPath(path:$path, locale:$locale) '
    "{ id content } } }"
)

# 사용자가 Wiki.js에서 dho/<category>/<item_id> 페이지에 이 마커 이후로 내용을 추가하면,
# DB가 바뀌어서 페이지를 재생성할 때도 마커 이후 내용은 그대로 보존한다(마커 이전은 매번
# DB 기준으로 통째로 교체됨 — Wiki.js의 pages.update가 diff/병합이 아니라 전체 치환이라
# 별도 보존 로직 없이는 사용자가 추가한 내용이 다음 갱신 때 사라지는 문제가 있었음).
USER_CONTENT_MARKER = "<!-- dho:user-content -->"


def extract_user_content(existing_content: str) -> str | None:
    idx = existing_content.find(USER_CONTENT_MARKER)
    return existing_content[idx:] if idx != -1 else None
CREATE_PAGE = """
mutation($content:String!,$description:String!,$path:String!,$tags:[String]!,$title:String!){
  pages {
    create(content:$content, description:$description, editor:"markdown", isPublished:true,
           isPrivate:false, locale:"ko", path:$path, tags:$tags, title:$title) {
      responseResult { succeeded errorCode message }
      page { id }
    }
  }
}
"""
UPDATE_PAGE = """
mutation($id:Int!,$content:String!,$description:String!,$tags:[String]!,$title:String!){
  pages {
    update(id:$id, content:$content, description:$description, isPublished:true, tags:$tags, title:$title) {
      responseResult { succeeded errorCode message }
    }
  }
}
"""


def find_existing_page(client: WikiClient, path: str) -> dict | None:
    data = client.gql(SINGLE_BY_PATH, {"path": path, "locale": "ko"}, allow_errors=True)
    return data.get("data", {}).get("pages", {}).get("singleByPath")


def upsert_page(client: WikiClient, path: str, title: str, description: str, content: str, tags: list[str]) -> str:
    # Wiki.js 2.5.314는 페이지 생성 시 내부 "rebuild-tree" 작업이 동시 요청을 못 견디고
    # pageTree 제약조건 위반으로 깨지는 걸 확인함 — 실제 쓰기(존재 확인+create/update)는
    # 전역 락으로 직렬화해서 항상 한 번에 하나씩만 Wiki.js에 도달하게 한다.
    with _write_lock:
        for attempt in range(1, WRITE_MAX_RETRIES + 1):
            try:
                existing = find_existing_page(client, path)
                if existing is None:
                    data = client.gql(CREATE_PAGE, {
                        "content": content, "description": description, "path": path, "tags": tags, "title": title,
                    })
                    result = data["data"]["pages"]["create"]["responseResult"]
                    if not result["succeeded"]:
                        raise RuntimeError(f"페이지 생성 실패 ({path}): {result['message']}")
                    return "created"
                else:
                    user_content = extract_user_content(existing.get("content") or "")
                    final_content = f"{content.rstrip()}\n\n{user_content}\n" if user_content else content
                    data = client.gql(UPDATE_PAGE, {
                        "id": existing["id"], "content": final_content, "description": description, "tags": tags, "title": title,
                    })
                    result = data["data"]["pages"]["update"]["responseResult"]
                    if not result["succeeded"]:
                        raise RuntimeError(f"페이지 갱신 실패 ({path}): {result['message']}")
                    return "updated"
            except RuntimeError:
                if attempt == WRITE_MAX_RETRIES:
                    raise
                time.sleep(1)


def wiki_href(category: str, item_id: int) -> str:
    return f"/dho/{category}/{item_id}"


def render_text_with_links(text: str | None, links: list[dict]) -> str:
    """dho_webapp.py의 render_text_with_links()와 동일한 로직(HTML 대신 Markdown 링크 생성)."""
    text = text or ""
    pieces: list[str] = []
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
            pieces.append(text[pos:idx])
        pieces.append(f"[{label}]({wiki_href(link['category'], link['item_id'])})")
        pos = idx + len(label)
    if pos < len(text):
        pieces.append(text[pos:])
    result = "".join(pieces)
    for link in unmatched:
        result += f" [{link.get('text', '')}]({wiki_href(link['category'], link['item_id'])})"
    return result


def md_table_cell(text: str) -> str:
    return (text or "").replace("\n", " ").replace("|", "\\|").strip()


def render_table_cell(cell: dict) -> str:
    text = render_text_with_links(cell.get("text"), cell.get("links"))
    return md_table_cell(text)


def build_markdown(db: psycopg.Connection, category: str, item_id: int, name: str, description: str | None) -> str:
    parts: list[str] = [f"# {name}"]
    if description:
        parts.append(description)

    attr_rows = db.execute(
        "SELECT label, text, links_json, images_json, position FROM raw_attrs "
        "WHERE category = %s AND item_id = %s ORDER BY position, insert_seq",
        (category, item_id),
    ).fetchall()
    table_rows = db.execute(
        "SELECT label, headers_json, rows_json, position FROM raw_tables "
        "WHERE category = %s AND item_id = %s ORDER BY position, insert_seq",
        (category, item_id),
    ).fetchall()

    if attr_rows:
        attr_lines = ["## 속성"]
        for row in attr_rows:
            links = json.loads(row["links_json"]) if row["links_json"] else []
            text = render_text_with_links(row["text"], links)
            attr_lines.append(f"- **{row['label']}**: {text}")
            images = json.loads(row["images_json"]) if row["images_json"] else []
            for img in images:
                caption = f" \"{img['caption']}\"" if img.get("caption") else ""
                attr_lines.append(f"  ![{img.get('alt', '')}]({img['src']}{caption})")
        parts.append("\n".join(attr_lines))

    label_counts: dict[str, int] = {}
    for tr in table_rows:
        label_counts[tr["label"]] = label_counts.get(tr["label"], 0) + 1
    for tr in table_rows:
        headers = json.loads(tr["headers_json"])
        heading = tr["label"]
        if label_counts[tr["label"]] > 1 and headers:
            heading = f"{tr['label']} — {headers[0]}"
        table_lines = [f"### {heading}"]
        if headers:
            table_lines.append("| " + " | ".join(md_table_cell(h) for h in headers) + " |")
            table_lines.append("|" + "|".join(["---"] * len(headers)) + "|")
        for row in json.loads(tr["rows_json"]):
            table_lines.append("| " + " | ".join(render_table_cell(c) for c in row) + " |")
        parts.append("\n".join(table_lines))

    return "\n\n".join(parts) + "\n"


def content_hash(content: str, title: str, description: str, tags: list[str]) -> str:
    payload = json.dumps({"content": content, "title": title, "description": description, "tags": tags}, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_category_label(db: psycopg.Connection, slug: str) -> str:
    row = db.execute("SELECT label_ko FROM category_localization WHERE slug = %s", (slug,)).fetchone()
    return row["label_ko"] if row else slug


def build_root_index_markdown(db: psycopg.Connection) -> str:
    """대분류별 카테고리 목록을 담은 최상위 dho 페이지 콘텐츠. dho_webapp.py 홈 화면과
    같은 category_localization(group_title_ko/group_order/order_in_group)을 재사용한다."""
    groups = db.execute(
        "SELECT slug, label_ko, group_title_ko FROM category_localization "
        "ORDER BY group_order, order_in_group"
    ).fetchall()
    counts = {
        r["category"]: r["c"]
        for r in db.execute("SELECT category, COUNT(*) c FROM items_core GROUP BY category").fetchall()
    }

    lines_by_group: dict[str, list[str]] = {}
    group_order: list[str] = []
    for row in groups:
        title = row["group_title_ko"]
        if title not in lines_by_group:
            lines_by_group[title] = []
            group_order.append(title)
        count = counts.get(row["slug"], 0)
        lines_by_group[title].append(f"- [{row['label_ko']}](/dho/{row['slug']}) — {count}건")

    parts = ["# DHO 아카이브", "## 가이드 / 팁\n- [가이드 홈](/guides)"]
    for title in group_order:
        parts.append(f"## {title}\n" + "\n".join(lines_by_group[title]))
    return "\n\n".join(parts) + "\n"


def build_category_index_markdown(db: psycopg.Connection, category: str, label: str) -> str:
    """카테고리 안 전체 항목 링크 목록을 담은 dho/<category> 페이지 콘텐츠."""
    items = db.execute(
        "SELECT item_id, name, title FROM items_core WHERE category = %s ORDER BY item_id",
        (category,),
    ).fetchall()
    lines = [
        f"- [{item['name'] or item['title'] or item['item_id']}](/dho/{category}/{item['item_id']})"
        for item in items
    ]
    return f"# {label}\n\n{len(items)}건\n\n" + "\n".join(lines) + "\n"


GUIDES_STUB_CONTENT = (
    "# 가이드 / 팁\n\n"
    "DB 데이터(도감)에 넣기 애매한 공략, 팁, 참고 자료는 이 페이지 아래 경로에 자유롭게 "
    "새 문서를 만들어서 정리하세요 (예: `guides/무역-루트`). 작성한 내용은 chat 챗봇의 "
    "시맨틱 검색에도 자동으로 반영됩니다.\n\n"
    "이 페이지 자체에 내용을 덧붙이고 싶다면 `<!-- dho:user-content -->` 마커를 추가한 뒤 "
    "그 아래에 자유롭게 작성하세요 — 재실행 시에도 마커 아래 내용은 보존됩니다.\n"
)


def ensure_state_table(db: psycopg.Connection) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS wiki_page_state (
            category TEXT NOT NULL,
            item_id INTEGER NOT NULL,
            content_hash TEXT NOT NULL,
            synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (category, item_id)
        )
        """
    )
    db.commit()


def sync_item(client: WikiClient, category: str, label: str, item: dict) -> str:
    """워커 스레드에서 실행 — 항목 하나를 동기화하고 "created"/"updated"/"skipped"를 반환."""
    db = get_conn()
    item_id = item["item_id"]
    name = item["name"] or item["title"] or str(item_id)
    content = build_markdown(db, category, item_id, name, item["description"])
    description = (item["description"] or label)[:250]
    tags = [category]
    chash = content_hash(content, name, description, tags)

    row = db.execute(
        "SELECT content_hash FROM wiki_page_state WHERE category = %s AND item_id = %s",
        (category, item_id),
    ).fetchone()
    if row and row["content_hash"] == chash:
        return "skipped"

    path = f"dho/{category}/{item_id}"
    action = upsert_page(client, path, name, description, content, tags)
    db.execute(
        "INSERT INTO wiki_page_state (category, item_id, content_hash) VALUES (%s, %s, %s) "
        "ON CONFLICT (category, item_id) DO UPDATE SET content_hash = EXCLUDED.content_hash, synced_at = now()",
        (category, item_id, chash),
    )
    db.commit()
    return action


def sync_category(db: psycopg.Connection, client: WikiClient, category: str, concurrency: int) -> tuple[int, int, int]:
    label = get_category_label(db, category)
    items = db.execute(
        "SELECT item_id, name, title, description FROM items_core WHERE category = %s ORDER BY item_id",
        (category,),
    ).fetchall()

    counts = {"created": 0, "updated": 0, "skipped": 0}
    errors: list[tuple[int, Exception]] = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(sync_item, client, category, label, item): item["item_id"] for item in items}
        for future in futures:
            item_id = futures[future]
            try:
                counts[future.result()] += 1
            except Exception as e:  # 항목 하나 실패해도 나머지는 계속 진행
                errors.append((item_id, e))

    if errors:
        print(f"[wikijs] {category}: {len(errors)}건 실패 — 예: item_id={errors[0][0]} {errors[0][1]}")
    print(
        f"[wikijs] {category} ({label}): 생성 {counts['created']}, 갱신 {counts['updated']}, "
        f"변경없음 {counts['skipped']}, 실패 {len(errors)} (총 {len(items)}건)"
    )
    return counts["created"], counts["updated"], counts["skipped"]


def sync_root_index(db: psycopg.Connection, client: WikiClient) -> None:
    content = build_root_index_markdown(db)
    action = upsert_page(client, "dho", "DHO 아카이브", "DHO 게임 데이터 아카이브 홈", content, ["index"])
    print(f"[wikijs] 루트 인덱스(dho): {action}")


def sync_category_index(db: psycopg.Connection, client: WikiClient, category: str, label: str) -> None:
    content = build_category_index_markdown(db, category, label)
    action = upsert_page(client, f"dho/{category}", label, f"{label} 목록", content, [category, "index"])
    print(f"[wikijs] 카테고리 인덱스({category}): {action}")


def sync_guides_stub(client: WikiClient) -> None:
    action = upsert_page(client, "guides", "가이드 / 팁", "자유 형식 가이드/팁 문서 모음", GUIDES_STUB_CONTENT, ["guides"])
    print(f"[wikijs] guides stub: {action}")


NAV_TREE_QUERY = (
    "{ navigation { tree { locale items { id kind label icon targetType target "
    "visibilityMode visibilityGroups } } } }"
)
NAV_UPDATE_TREE = (
    "mutation($tree:[NavigationTreeInput]!){ navigation { updateTree(tree:$tree) { "
    "responseResult { succeeded errorCode message } } } }"
)
NAV_LOCALE = "ko"
NAV_EXTRA_ITEMS = [
    {"id": "dho-home", "kind": "link", "label": "DHO 아카이브", "icon": "mdi-book-open-page-variant",
     "targetType": "page", "target": "/dho", "visibilityMode": "all", "visibilityGroups": None},
    {"id": "dho-guides", "kind": "link", "label": "가이드 / 팁", "icon": "mdi-lightbulb-on",
     "targetType": "page", "target": "/guides", "visibilityMode": "all", "visibilityGroups": None},
]


def ensure_navigation(client: WikiClient) -> None:
    """Wiki.js 사이드바 Navigation에 dho/guides 항목이 없으면 추가한다(기존 트리 보존,
    id 기준으로 이미 있으면 건드리지 않아 관리자가 직접 수정한 내용도 유지됨)."""
    data = client.gql(NAV_TREE_QUERY)
    trees = data["data"]["navigation"]["tree"]
    tree = next((t for t in trees if t["locale"] == NAV_LOCALE), None)
    items = list(tree["items"]) if tree else []
    existing_ids = {i["id"] for i in items}
    missing = [extra for extra in NAV_EXTRA_ITEMS if extra["id"] not in existing_ids]
    if not missing:
        return
    items.extend(missing)
    clean_items = [
        {k: i.get(k) for k in ("id", "kind", "label", "icon", "targetType", "target", "visibilityMode", "visibilityGroups")}
        for i in items
    ]
    data = client.gql(NAV_UPDATE_TREE, {"tree": [{"locale": NAV_LOCALE, "items": clean_items}]})
    status = data["data"]["navigation"]["updateTree"]["responseResult"]
    if not status["succeeded"]:
        raise RuntimeError(f"Navigation 갱신 실패: {status['message']}")
    print(f"[wikijs] Navigation에 {len(missing)}개 항목 등록: {[m['label'] for m in missing]}")


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--categories", help="쉼표로 구분된 카테고리 목록 (예: tarotCard,cannon)")
    group.add_argument("--all", action="store_true", help="전체 카테고리")
    parser.add_argument("--concurrency", type=int, default=8, help="카테고리 내 동시 처리 항목 수 (기본 8)")
    args = parser.parse_args()

    db = psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=False)
    ensure_state_table(db)

    if args.all:
        categories = [r["category"] for r in db.execute("SELECT DISTINCT category FROM items_core ORDER BY category")]
    else:
        categories = [c.strip() for c in args.categories.split(",") if c.strip()]

    client = WikiClient()
    totals = [0, 0, 0]
    for category in categories:
        c, u, s = sync_category(db, client, category, args.concurrency)
        totals[0] += c
        totals[1] += u
        totals[2] += s
        sync_category_index(db, client, category, get_category_label(db, category))

    sync_root_index(db, client)
    sync_guides_stub(client)
    ensure_navigation(client)

    db.close()
    print(f"[wikijs] 전체 완료 — 생성 {totals[0]}, 갱신 {totals[1]}, 변경없음 {totals[2]}")


if __name__ == "__main__":
    main()
