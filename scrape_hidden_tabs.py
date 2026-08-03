#!/usr/bin/env python3
"""
탭 전환으로만 노출되는 획득 방법 표를 Playwright로 추가 수집하는 스크립트

배경
----
기존 scraper.py는 순수 HTTP 요청이라, 클라이언트 사이드 탭 전환으로만 렌더링되는
표(예: 해양조합 등록증의 "해상 NPC" 탭 - 함대 수/해역 정보)를 캡처하지 못했다.
전체 33,496건 중 약 3,365건(카테고리별 몰림: consumable/equipment/tradeGoods/
field/city/sea/cannon 등)이 영향을 받는 것으로 확인됨 (2026-07-31).

이 스크립트는 해당 항목만 골라 실제 브라우저로 탭을 하나씩 클릭하고, 기존
raw_tables/raw_attrs에 없는 새 표/속성만 추가 삽입한다 (기존 행은 건드리지 않음).
재실행 시 hidden_tabs_progress 테이블을 보고 이미 처리한 URL은 건너뛴다.

사용법
------
    python scrape_hidden_tabs.py scan             # 영향 항목 개수만 확인 (드라이런)
    python scrape_hidden_tabs.py run              # 전체 크롤링 + DB 반영
    python scrape_hidden_tabs.py run --limit 20   # 일부만 테스트
    python scrape_hidden_tabs.py run --retry-errors  # status='error'였던 항목 재시도
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_structured_db import CACHE_DB, STRUCT_DB, extract_detail

import sqlite3
from playwright.sync_api import sync_playwright

# 클릭 대상(=현재 비활성 탭) 버튼에만 붙는 클래스 조합. certificate/1898 실측으로 확인.
INACTIVE_MARKER = (
    "border-b-2 px-2.5 py-1 text-[11px] font-semibold "
    "border-transparent text-muted-foreground hover:text-foreground"
)
DEFAULT_DELAY = 1.0
MAX_TABS_PER_ITEM = 8  # 무한루프 방지용 안전장치
PER_ITEM_DEADLINE_SEC = 45  # 개별 항목 처리 최대 허용 시간(초) — 이 이상 걸리면 강제 중단


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(STRUCT_DB)
    conn.execute(f"ATTACH DATABASE '{CACHE_DB}' AS cache")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS hidden_tabs_progress (
            url TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            new_tables INTEGER DEFAULT 0,
            new_attrs INTEGER DEFAULT 0,
            error TEXT,
            done_at TEXT
        );
        """
    )
    conn.commit()
    return conn


def find_affected_items(conn: sqlite3.Connection) -> list[tuple[str, int, str]]:
    """숨은 탭 마커가 원본 HTML에 있는 (category, item_id, url) 목록."""
    rows = conn.execute(
        """
        SELECT ic.category, ic.item_id, ic.url, cp.html
        FROM items_core ic
        JOIN cache.pages cp ON cp.url = ic.url
        """
    ).fetchall()
    affected = [(c, i, u) for c, i, u, html in rows if INACTIVE_MARKER in html]
    return affected


def existing_signatures(
    conn: sqlite3.Connection, category: str, item_id: int
) -> tuple[set, set]:
    table_sigs = set()
    for label, headers_json in conn.execute(
        "SELECT label, headers_json FROM raw_tables WHERE category=? AND item_id=?",
        (category, item_id),
    ):
        table_sigs.add((label, tuple(json.loads(headers_json))))
    attr_sigs = set()
    for label, text in conn.execute(
        "SELECT label, text FROM raw_attrs WHERE category=? AND item_id=?",
        (category, item_id),
    ):
        attr_sigs.add((label, text))
    return table_sigs, attr_sigs


def crawl_one(page, url: str, table_sigs: set, attr_sigs: set) -> tuple[list, list]:
    """페이지의 숨은 탭을 전부 클릭하며, 기존 시그니처에 없는 새 표/속성만 모은다."""
    page.goto(url, wait_until="domcontentloaded", timeout=20000)
    page.wait_for_timeout(500)

    visited: set[str] = set()
    new_tables: list[dict] = []
    new_attrs: list[dict] = []

    start = time.monotonic()
    for _ in range(MAX_TABS_PER_ITEM):
        if time.monotonic() - start > PER_ITEM_DEADLINE_SEC:
            break
        buttons = page.query_selector_all("button")
        candidate = None
        for b in buttons:
            cls = b.get_attribute("class") or ""
            if cls.strip() == INACTIVE_MARKER or all(
                tok in cls for tok in INACTIVE_MARKER.split()
            ):
                label = b.inner_text().strip()
                if label and label not in visited:
                    candidate = label
                    break
        if candidate is None:
            break
        visited.add(candidate)
        try:
            page.get_by_role("button", name=candidate, exact=True).first.click(timeout=3000)
        except Exception:
            continue
        page.wait_for_timeout(350)

        detail = extract_detail(page.content())
        if detail is None:
            continue
        for t in detail["tables"]:
            sig = (t["label"], tuple(t["headers"]))
            if sig not in table_sigs:
                table_sigs.add(sig)
                new_tables.append(t)
        for a in detail["attrs"]:
            sig = (a["label"], a["text"])
            if sig not in attr_sigs:
                attr_sigs.add(sig)
                new_attrs.append(a)

    return new_tables, new_attrs


def run(limit: int | None, retry_errors: bool, delay: float) -> None:
    conn = get_conn()
    affected = find_affected_items(conn)
    print(f"[대상] 숨은 탭 보유 항목: {len(affected)}건")

    done_statuses = {"ok", "no_new_data"} if not retry_errors else {"ok", "no_new_data", "error"}
    done_urls = set()
    for url, status in conn.execute("SELECT url, status FROM hidden_tabs_progress"):
        if status in done_statuses:
            done_urls.add(url)

    targets = [(c, i, u) for c, i, u in affected if u not in done_urls]
    if limit:
        targets = targets[:limit]
    print(f"[대상] 이번 실행에서 처리할 항목: {len(targets)}건")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_default_timeout(10000)
        page.set_default_navigation_timeout(15000)
        page.on("dialog", lambda d: d.dismiss())

        n_ok = n_new_data = n_error = 0
        for idx, (category, item_id, url) in enumerate(targets, 1):
            if idx > 1 and idx % 200 == 0:
                # 장시간 실행 시 누적되는 브라우저 메모리/DOM 누수 방지를 위해 주기적으로 재생성
                page.close()
                page = browser.new_page()
                page.set_default_timeout(10000)
                page.set_default_navigation_timeout(15000)
                page.on("dialog", lambda d: d.dismiss())

            table_sigs, attr_sigs = existing_signatures(conn, category, item_id)
            try:
                new_tables, new_attrs = crawl_one(page, url, table_sigs, attr_sigs)
            except Exception as e:
                conn.execute(
                    """INSERT INTO hidden_tabs_progress (url, status, error, done_at)
                       VALUES (?, 'error', ?, datetime('now'))
                       ON CONFLICT(url) DO UPDATE SET
                         status='error', error=excluded.error, done_at=excluded.done_at""",
                    (url, str(e)[:500]),
                )
                conn.commit()
                n_error += 1
                print(f"  [{idx}/{len(targets)}] ERROR {url}: {e}")
                continue

            for t in new_tables:
                conn.execute(
                    "INSERT INTO raw_tables (category, item_id, label, headers_json, rows_json) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        category,
                        item_id,
                        t["label"],
                        json.dumps(t["headers"], ensure_ascii=False),
                        json.dumps(t["rows"], ensure_ascii=False),
                    ),
                )
            for a in new_attrs:
                conn.execute(
                    "INSERT INTO raw_attrs (category, item_id, label, text, links_json) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (category, item_id, a["label"], a["text"], json.dumps(a["links"], ensure_ascii=False)),
                )

            status = "ok" if (new_tables or new_attrs) else "no_new_data"
            conn.execute(
                """INSERT INTO hidden_tabs_progress (url, status, new_tables, new_attrs, done_at)
                   VALUES (?, ?, ?, ?, datetime('now'))
                   ON CONFLICT(url) DO UPDATE SET
                     status=excluded.status, new_tables=excluded.new_tables,
                     new_attrs=excluded.new_attrs, error=NULL, done_at=excluded.done_at""",
                (url, status, len(new_tables), len(new_attrs)),
            )
            conn.commit()
            n_ok += 1
            if new_tables or new_attrs:
                n_new_data += 1
            if idx % 50 == 0 or idx == len(targets):
                print(
                    f"  [{idx}/{len(targets)}] 진행 중 (성공 {n_ok}, 신규데이터 {n_new_data}, 오류 {n_error})"
                )
            time.sleep(delay)

        browser.close()

    print(f"[완료] 성공 {n_ok}, 신규데이터 발견 {n_new_data}, 오류 {n_error}")
    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="숨은 탭 데이터 추가 수집")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("scan", help="영향 항목 개수만 확인 (드라이런)")

    p_run = sub.add_parser("run", help="실제 크롤링 실행")
    p_run.add_argument("--limit", type=int, default=None)
    p_run.add_argument("--retry-errors", action="store_true")
    p_run.add_argument("--delay", type=float, default=DEFAULT_DELAY)

    args = parser.parse_args()

    if args.command == "scan":
        conn = get_conn()
        affected = find_affected_items(conn)
        print(f"숨은 탭 보유 항목: {len(affected)}건")
        conn.close()
    elif args.command == "run":
        run(args.limit, args.retry_errors, args.delay)


if __name__ == "__main__":
    main()
