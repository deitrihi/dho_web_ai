#!/usr/bin/env python3
"""
dho_structured.sqlite3의 "원본성" 테이블(items_core/raw_attrs/raw_tables/
category_localization)을 PostgreSQL로 옮기는 1회성 부트스트랩 스크립트.

이 4개는 build_structured_db.py/build_category_localization.py(재크롤링 시에만 도는
드문 작업, SQLite에 그대로 유지)가 만드는 "원본" 데이터다. 나머지 파생 테이블
(item_backlinks/item_acquisition_*/카테고리 전용 테이블 등)은 이 스크립트가 옮기지 않고,
이 스크립트 실행 후 Postgres 위에서 build_backlinks.py/build_acquisition.py/
materialize_*.py/build_search_index.py를 직접 실행해서 만든다.

사용법
------
    python migrate_to_postgres.py [--sqlite-path dho_structured.sqlite3]

접속 정보는 DATABASE_URL 환경변수(있으면 그대로 사용) 또는 POSTGRES_USER/
POSTGRES_PASSWORD/POSTGRES_DB(+선택적 POSTGRES_HOST/POSTGRES_PORT, 기본 localhost:5432)
조합에서 읽는다.
"""
import argparse
import os
import sqlite3
from pathlib import Path

import psycopg

# (SQLite 테이블명, Postgres CREATE TABLE 본문) — build_structured_db.py/
# build_category_localization.py의 스키마를 그대로 옮긴 것(SQLite INTEGER/TEXT는
# Postgres INTEGER/TEXT로 1:1 대응, 이 4개 테이블엔 그 외 타입이 없음을 확인함).
TABLE_DDL = {
    "items_core": """
        CREATE TABLE items_core (
            category TEXT NOT NULL,
            item_id INTEGER NOT NULL,
            name TEXT,
            title TEXT,
            description TEXT,
            url TEXT,
            PRIMARY KEY (category, item_id)
        )
    """,
    # insert_seq: SQLite의 암묵적 rowid를 대신해서(Postgres엔 없음) dho_webapp.py의
    # "ORDER BY position, rowid" 안정 정렬을 그대로 재현하기 위한 삽입순서 컬럼.
    "raw_attrs": """
        CREATE TABLE raw_attrs (
            category TEXT NOT NULL,
            item_id INTEGER NOT NULL,
            label TEXT NOT NULL,
            text TEXT,
            links_json TEXT,
            images_json TEXT,
            position INTEGER NOT NULL DEFAULT 0,
            insert_seq SERIAL
        )
    """,
    "raw_tables": """
        CREATE TABLE raw_tables (
            category TEXT NOT NULL,
            item_id INTEGER NOT NULL,
            label TEXT NOT NULL,
            headers_json TEXT NOT NULL,
            rows_json TEXT NOT NULL,
            position INTEGER NOT NULL DEFAULT 0,
            insert_seq SERIAL
        )
    """,
    "category_localization": """
        CREATE TABLE category_localization (
            slug TEXT PRIMARY KEY,
            label_ko TEXT NOT NULL,
            group_title_ko TEXT NOT NULL,
            group_flag TEXT NOT NULL,
            group_order INTEGER NOT NULL,
            order_in_group INTEGER NOT NULL
        )
    """,
}

INDEX_DDL = {
    "raw_attrs": ["CREATE INDEX idx_raw_attrs_item ON raw_attrs (category, item_id)"],
    "raw_tables": ["CREATE INDEX idx_raw_tables_item ON raw_tables (category, item_id)"],
}


def pg_dsn() -> str:
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    db = os.environ["POSTGRES_DB"]
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def migrate_table(sqlite_conn: sqlite3.Connection, pg_conn: psycopg.Connection, table: str) -> None:
    with pg_conn.cursor() as cur:
        cur.execute(f'DROP TABLE IF EXISTS "{table}"')
        cur.execute(TABLE_DDL[table])

    sqlite_cur = sqlite_conn.execute(f'SELECT * FROM "{table}"')
    columns = [d[0] for d in sqlite_cur.description]
    col_list = ", ".join(f'"{c}"' for c in columns)

    n = 0
    with pg_conn.cursor() as cur:
        with cur.copy(f'COPY "{table}" ({col_list}) FROM STDIN') as copy:
            for row in sqlite_cur:
                copy.write_row(row)
                n += 1

    if table in INDEX_DDL:
        with pg_conn.cursor() as cur:
            for idx_sql in INDEX_DDL[table]:
                cur.execute(idx_sql)

    pg_conn.commit()
    print(f"[migrate] {table}: {n}건 적재")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sqlite-path",
        default=str(Path(__file__).parent / "dho_structured.sqlite3"),
        help="원본 SQLite 파일 경로 (기본: ./dho_structured.sqlite3)",
    )
    args = parser.parse_args()

    sqlite_conn = sqlite3.connect(f"file:{args.sqlite_path}?mode=ro", uri=True)
    pg_conn = psycopg.connect(pg_dsn())
    try:
        for table in ("items_core", "raw_attrs", "raw_tables", "category_localization"):
            migrate_table(sqlite_conn, pg_conn, table)
    finally:
        sqlite_conn.close()
        pg_conn.close()
    print("[migrate] 완료 — 이어서 build_backlinks.py/build_acquisition.py/"
          "materialize_*.py/build_search_index.py를 Postgres 대상으로 실행하세요.")


if __name__ == "__main__":
    main()
