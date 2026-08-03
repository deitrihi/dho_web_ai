#!/usr/bin/env python3
"""
dho-archive.vercel.app 전체 데이터 크롤러

설계 원칙
---------
1. 원본 HTML을 그대로 SQLite에 캐싱한다 (구조화 파싱은 다음 단계).
   -> 사이트에 두 번 부담 주지 않기 위해, 한 번 받은 페이지는 다시 받지 않는다.
2. 목록(list) 페이지 크롤링과 상세(detail) 페이지 크롤링을 분리한다.
   -> 목록 페이지는 카테고리당 수십~수백 개뿐이라 빠르게 끝난다.
   -> 상세 페이지는 33,000개가 넘으므로 시간이 오래 걸리고, 중간에 끊겨도
      다시 실행하면 이어서 진행되도록(resumable) 만든다.
3. 요청 사이 delay를 기본으로 두어 사이트에 부담을 주지 않는다.

사용 예시
--------
    # 1) 카테고리 목록 확인
    python scraper.py discover

    # 2) 모든 카테고리의 "목록 페이지" 크롤링 (id + 이름 수집)
    python scraper.py crawl-lists --all

    # 3) 특정 카테고리만
    python scraper.py crawl-lists --categories cannon,recipe,recipeBook

    # 4) 상세 페이지 크롤링 (목록에서 수집된 id 기준으로 이어서 진행)
    python scraper.py crawl-details --all --delay 0.8

    # 5) 진행 상황 확인
    python scraper.py status
"""
import argparse
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://dho-archive.vercel.app"
DB_PATH = Path(__file__).parent / "dho_cache.sqlite3"
USER_AGENT = "Mozilla/5.0 (compatible; dho-local-archiver/0.1; personal research use)"
DEFAULT_DELAY = 1.0  # 요청 사이 대기 시간(초). 사이트에 부담 주지 않기 위한 기본값.
TIMEOUT = 15
MAX_RETRIES = 3

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})


# ---------------------------------------------------------------------------
# DB 초기화
# ---------------------------------------------------------------------------
def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS pages (
            url TEXT PRIMARY KEY,
            html TEXT NOT NULL,
            fetched_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS categories (
            slug TEXT PRIMARY KEY,
            label TEXT,
            total_count INTEGER,
            list_crawled INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS items (
            category TEXT NOT NULL,
            item_id INTEGER NOT NULL,
            name TEXT,
            list_page INTEGER,
            detail_crawled INTEGER DEFAULT 0,
            PRIMARY KEY (category, item_id)
        );

        CREATE INDEX IF NOT EXISTS idx_items_detail_crawled
            ON items (detail_crawled);
        """
    )
    conn.commit()


# ---------------------------------------------------------------------------
# 네트워크 유틸
# ---------------------------------------------------------------------------
def fetch(conn: sqlite3.Connection, url: str, delay: float, force: bool = False) -> str:
    """URL의 HTML을 가져온다. 이미 캐시에 있으면 네트워크 요청 없이 반환한다."""
    if not force:
        row = conn.execute("SELECT html FROM pages WHERE url = ?", (url,)).fetchone()
        if row:
            return row[0]

    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            resp.encoding = "utf-8"  # 서버가 Content-Type에 charset을 명시하지 않아
            # requests가 기본값인 ISO-8859-1로 오판하는 것을 방지 (실제 응답은 UTF-8)
            html = resp.text
            conn.execute(
                "INSERT OR REPLACE INTO pages (url, html, fetched_at) VALUES (?, ?, ?)",
                (url, html, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
            time.sleep(delay)
            return html
        except requests.RequestException as e:
            last_err = e
            wait = 2 * attempt
            print(f"  [경고] {url} 요청 실패 ({attempt}/{MAX_RETRIES}): {e} -> {wait}s 대기 후 재시도")
            time.sleep(wait)
    raise RuntimeError(f"{url} 요청이 {MAX_RETRIES}회 모두 실패했습니다: {last_err}")


# ---------------------------------------------------------------------------
# 카테고리 목록 discover
# ---------------------------------------------------------------------------
def discover_categories(conn: sqlite3.Connection, delay: float) -> list[str]:
    html = fetch(conn, BASE_URL + "/", delay)
    soup = BeautifulSoup(html, "html.parser")

    found = {}
    for a in soup.find_all("a", href=True):
        m = re.search(r"^/db/([a-zA-Z]+)$", a["href"])
        if not m:
            continue
        slug = m.group(1)
        label = a.get_text(strip=True)
        # 링크 텍스트 뒤에 붙는 숫자(건수)는 형제 텍스트 노드로 오는 경우가 많아
        # 부모 요소 전체 텍스트에서 숫자만 따로 추출 시도
        count = None
        parent_text = a.parent.get_text(" ", strip=True) if a.parent else ""
        count_m = re.search(r"([\d,]+)\s*$", parent_text)
        if count_m:
            try:
                count = int(count_m.group(1).replace(",", ""))
            except ValueError:
                count = None
        found[slug] = (label, count)

    for slug, (label, count) in found.items():
        conn.execute(
            """INSERT INTO categories (slug, label, total_count) VALUES (?, ?, ?)
               ON CONFLICT(slug) DO UPDATE SET label=excluded.label,
                                               total_count=COALESCE(excluded.total_count, total_count)""",
            (slug, label, count),
        )
    conn.commit()
    return sorted(found.keys())


# ---------------------------------------------------------------------------
# 목록(list) 페이지 크롤링
# ---------------------------------------------------------------------------
def get_max_page(soup: BeautifulSoup, category: str) -> int:
    max_page = 1
    for a in soup.find_all("a", href=True):
        m = re.search(rf"/db/{re.escape(category)}\?.*page=(\d+)", a["href"])
        if m:
            max_page = max(max_page, int(m.group(1)))
    return max_page


def crawl_category_list(conn: sqlite3.Connection, category: str, delay: float) -> int:
    print(f"[목록] {category} 크롤링 시작")
    first_url = f"{BASE_URL}/db/{category}"
    html = fetch(conn, first_url, delay)
    soup = BeautifulSoup(html, "html.parser")
    max_page = get_max_page(soup, category)

    total_items = 0
    for page in range(1, max_page + 1):
        page_url = first_url if page == 1 else f"{first_url}?page={page}"
        page_html = html if page == 1 else fetch(conn, page_url, delay)
        page_soup = soup if page == 1 else BeautifulSoup(page_html, "html.parser")

        pattern = re.compile(rf"/db/{re.escape(category)}/(\d+)$")
        seen_on_page = set()
        for a in page_soup.find_all("a", href=True):
            m = pattern.search(a["href"])
            if not m:
                continue
            item_id = int(m.group(1))
            if item_id in seen_on_page:
                continue
            seen_on_page.add(item_id)
            name = a.get_text(strip=True)
            conn.execute(
                """INSERT INTO items (category, item_id, name, list_page) VALUES (?, ?, ?, ?)
                   ON CONFLICT(category, item_id) DO UPDATE SET name=excluded.name""",
                (category, item_id, name, page),
            )
        total_items += len(seen_on_page)
        conn.commit()
        print(f"  page {page}/{max_page}: {len(seen_on_page)}개 항목")

    conn.execute(
        "UPDATE categories SET list_crawled = 1 WHERE slug = ?", (category,)
    )
    conn.commit()
    print(f"[목록] {category} 완료: 총 {total_items}개 항목 발견")
    return total_items


# ---------------------------------------------------------------------------
# 상세(detail) 페이지 크롤링
# ---------------------------------------------------------------------------
def crawl_details(conn: sqlite3.Connection, categories: list[str] | None, delay: float, limit: int | None) -> None:
    query = "SELECT category, item_id FROM items WHERE detail_crawled = 0"
    params: list = []
    if categories:
        placeholders = ",".join("?" * len(categories))
        query += f" AND category IN ({placeholders})"
        params.extend(categories)
    query += " ORDER BY category, item_id"
    if limit:
        query += " LIMIT ?"
        params.append(limit)

    rows = conn.execute(query, params).fetchall()
    print(f"[상세] 크롤링 대상: {len(rows)}개")

    done = 0
    for category, item_id in rows:
        url = f"{BASE_URL}/db/{category}/{item_id}"
        try:
            fetch(conn, url, delay)
        except RuntimeError as e:
            print(f"  [실패] {url}: {e}")
            continue
        conn.execute(
            "UPDATE items SET detail_crawled = 1 WHERE category = ? AND item_id = ?",
            (category, item_id),
        )
        conn.commit()
        done += 1
        if done % 25 == 0:
            print(f"  진행: {done}/{len(rows)}")

    print(f"[상세] 완료: {done}개 크롤링")


# ---------------------------------------------------------------------------
# 상태 확인
# ---------------------------------------------------------------------------
def show_status(conn: sqlite3.Connection) -> None:
    cats = conn.execute(
        "SELECT slug, total_count, list_crawled FROM categories ORDER BY slug"
    ).fetchall()
    print(f"{'카테고리':<20}{'예상 건수':>10}{'목록완료':>8}{'수집됨':>8}{'상세완료':>8}")
    total_items = total_detail = 0
    for slug, total_count, list_crawled in cats:
        cnt = conn.execute(
            "SELECT COUNT(*), SUM(detail_crawled) FROM items WHERE category = ?", (slug,)
        ).fetchone()
        item_cnt = cnt[0] or 0
        detail_cnt = cnt[1] or 0
        total_items += item_cnt
        total_detail += detail_cnt
        print(
            f"{slug:<20}{(total_count or 0):>10}{'O' if list_crawled else '-':>8}"
            f"{item_cnt:>8}{detail_cnt:>8}"
        )
    print("-" * 60)
    print(f"합계: 수집된 항목 {total_items}개, 상세 완료 {total_detail}개")
    n_pages = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
    print(f"캐시된 페이지(HTML) 수: {n_pages}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="DHO 아카이브 전체 크롤러")
    sub = parser.add_subparsers(dest="command", required=True)

    p_discover = sub.add_parser("discover", help="카테고리 목록 확인")
    p_discover.add_argument("--delay", type=float, default=DEFAULT_DELAY)

    p_list = sub.add_parser("crawl-lists", help="목록 페이지 크롤링 (id/이름 수집)")
    p_list.add_argument("--all", action="store_true")
    p_list.add_argument("--categories", type=str, help="쉼표로 구분된 카테고리 슬러그")
    p_list.add_argument("--delay", type=float, default=DEFAULT_DELAY)

    p_detail = sub.add_parser("crawl-details", help="상세 페이지 크롤링")
    p_detail.add_argument("--all", action="store_true")
    p_detail.add_argument("--categories", type=str, help="쉼표로 구분된 카테고리 슬러그")
    p_detail.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    p_detail.add_argument("--limit", type=int, default=None, help="이번 실행에서 크롤링할 최대 개수")

    sub.add_parser("status", help="진행 상황 확인")

    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    if args.command == "discover":
        slugs = discover_categories(conn, args.delay)
        print(f"발견된 카테고리 {len(slugs)}개:")
        for s in slugs:
            print(f"  - {s}")

    elif args.command == "crawl-lists":
        if args.categories:
            targets = [c.strip() for c in args.categories.split(",") if c.strip()]
        elif args.all:
            existing = [r[0] for r in conn.execute("SELECT slug FROM categories").fetchall()]
            targets = existing or discover_categories(conn, args.delay)
        else:
            print("--all 또는 --categories 옵션이 필요합니다.")
            sys.exit(1)

        for cat in targets:
            crawl_category_list(conn, cat, args.delay)

    elif args.command == "crawl-details":
        if args.categories:
            targets = [c.strip() for c in args.categories.split(",")]
        elif args.all:
            targets = None
        else:
            print("--all 또는 --categories 옵션이 필요합니다.")
            sys.exit(1)
        crawl_details(conn, targets, args.delay, args.limit)

    elif args.command == "status":
        show_status(conn)

    conn.close()


if __name__ == "__main__":
    main()
