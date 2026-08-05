"""
title: DHO Text-to-SQL
author: dho-project
version: 0.1.0
description: dho_structured.sqlite3(대항해시대 온라인 아카이브 구조화 DB)를 자연어 질문에 맞춰
  탐색·조회하는 Text-to-SQL 도구. 질문에 아이템/직업/스킬 등 고유명사가 있으면 get_item_detail로
  이름 하나로 상세정보를 한 번에 조회하고, 그걸로 부족하면(관련 하위 테이블 조회, 조건별 집계 등)
  list_categories -> find_tables -> get_table_schema -> run_sql 순서로 세부 조회한다.
"""

import json
import sqlite3

from pydantic import BaseModel, Field

# item_id/row_index/position이나 "{라벨}_id" 외래키 컬럼은 수량이 아니라 식별자라서
# 콤마를 붙이면 "12,345" 같은 값처럼 오해할 수 있다 -> format_number 대상에서 제외한다.
_ID_LIKE_NAMES = {"item_id", "row_index", "position"}


def format_number(value):
    """정수/실수 값을 세자리마다 콤마를 넣은 문자열로 바꾼다. 숫자가 아니면 그대로 반환한다."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    return f"{value:,}"


def _format_row(row: dict) -> dict:
    return {
        k: (v if k in _ID_LIKE_NAMES or k.endswith("_id") else format_number(v))
        for k, v in row.items()
    }


class Tools:
    class Valves(BaseModel):
        db_path: str = Field(
            default="/data/dbsql/dho_structured.sqlite3",
            description="읽기 전용으로 마운트된 DHO 구조화 SQLite DB 경로",
        )
        max_rows: int = Field(
            default=200,
            description="run_sql 결과로 반환할 최대 행 수",
        )

    def __init__(self):
        self.valves = self.Valves()

    def _connect(self):
        return sqlite3.connect(f"file:{self.valves.db_path}?mode=ro", uri=True)

    def _acquisition_info(self, con, category: str, item_id: int) -> dict:
        """item_acquisition_*/item_transmutation_*/item_detail_list 공유 테이블에서
        이 아이템의 획득처/변성연금 정보를 전부 모아 온다. 이 테이블들은 카테고리 전용
        테이블(예: certificate)과 별도로 존재해서, item_id로 직접 조인하지 않으면
        검색에서 누락되기 쉽다."""
        shared_tables = [
            r[0]
            for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND "
                "(name LIKE 'item_acquisition_%' OR name LIKE 'item_transmutation_%' "
                "OR name = 'item_detail_list')"
            ).fetchall()
        ]
        info = {}
        for table in shared_tables:
            cols = {r[1] for r in con.execute(f'PRAGMA table_info("{table}")')}
            if not {"category", "item_id"} <= cols:
                continue
            cur = con.execute(
                f'SELECT * FROM "{table}" WHERE category = ? AND item_id = ?',
                (category, item_id),
            )
            col_names = [d[0] for d in cur.description]
            rows = [dict(zip(col_names, r)) for r in cur.fetchall()]
            if rows:
                info[table] = rows
        return info

    def list_categories(self) -> str:
        """
        대항해시대 온라인 아카이브 DB에 존재하는 70개 아이템/컨텐츠 카테고리 이름과
        카테고리별 항목 수를 반환한다. 질문과 관련된 카테고리가 뭔지 모를 때 가장 먼저 호출한다.
        """
        con = self._connect()
        try:
            rows = con.execute(
                "SELECT category, COUNT(*) FROM items_core GROUP BY category ORDER BY category"
            ).fetchall()
        finally:
            con.close()
        return json.dumps(
            [{"category": c, "count": n} for c, n in rows], ensure_ascii=False
        )

    def get_item_detail(self, keyword: str) -> str:
        """
        아이템/직업/스킬 등 고유명사(예: "준사관", "갈레온")로 검색해서 해당 항목의 상세
        정보를 한 번의 호출로 전부 반환한다. 질문에 특정 이름이 나오면 다른 함수보다
        이 함수를 가장 먼저 시도한다 (search_items + get_table_schema + run_sql을 합친
        것과 같아서 별도로 이어서 호출할 필요가 없다). 동명이인처럼 여러 건이 매칭되면
        전부 반환하니 그중 질문에 맞는 것을 고르면 된다.
        결과의 "획득_방법" 필드에는 판매 NPC/퀘스트/해상 NPC/레시피/변성연금 등 공유
        테이블(item_acquisition_*, item_transmutation_*)에서 찾은 이 아이템의 실제
        획득 경로가 전부 들어있다 — "이 아이템 어디서 구하나" 질문은 여기만 보면 된다.

        :param keyword: 검색할 아이템/직업/컨텐츠 이름 (전체 또는 일부)
        """
        con = self._connect()
        try:
            matches = con.execute(
                "SELECT category, item_id, name, title, description FROM items_core "
                "WHERE name LIKE ? OR title LIKE ? LIMIT 10",
                (f"%{keyword}%", f"%{keyword}%"),
            ).fetchall()
            results = []
            for category, item_id, name, title, description in matches:
                entry = {
                    "category": category,
                    "item_id": item_id,
                    "name": name,
                    "title": title,
                    "description": description,
                }
                table_exists = con.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    (category,),
                ).fetchone()
                if table_exists:
                    cur = con.execute(
                        f'SELECT * FROM "{category}" WHERE item_id = ?', (item_id,)
                    )
                    cols = [d[0] for d in cur.description]
                    row = cur.fetchone()
                    if row:
                        entry["detail"] = dict(zip(cols, row))
                acquisition = self._acquisition_info(con, category, item_id)
                if acquisition:
                    entry["획득_방법"] = acquisition
                results.append(entry)
        finally:
            con.close()
        return json.dumps(results, ensure_ascii=False)

    def search_items(self, keyword: str) -> str:
        """
        아이템/직업/스킬 등 고유명사(예: "준사관", "갈레온")로 전체 아이템 이름(items_core)을
        검색해서 그 이름이 어느 category와 item_id에 속하는지만 가볍게 찾는다. 상세 정보까지
        필요하면 이 함수 대신 get_item_detail을 바로 호출하는 게 낫다. 이 함수는 후보가 너무
        많아서 목록만 먼저 추리고 싶을 때, 또는 find_tables에서 결과가 안 나올 때 보조로 쓴다.

        :param keyword: 검색할 아이템/직업/컨텐츠 이름 (전체 또는 일부)
        """
        con = self._connect()
        try:
            rows = con.execute(
                "SELECT category, item_id, name, title FROM items_core "
                "WHERE name LIKE ? OR title LIKE ? LIMIT 30",
                (f"%{keyword}%", f"%{keyword}%"),
            ).fetchall()
        finally:
            con.close()
        return json.dumps(
            [
                {"category": c, "item_id": i, "name": n, "title": t}
                for c, i, n, t in rows
            ],
            ensure_ascii=False,
        )

    def find_tables(self, keyword: str) -> str:
        """
        테이블 이름에 keyword가 포함된 테이블 목록을 반환한다 (대소문자 무시).
        list_categories에서 찾은 카테고리 이름(영문)으로 검색해서 관련 테이블을 찾을 때
        사용한다. 예: keyword="ship" -> ship, shipMaterial, ship__기본 성능 등.
        질문에 나온 한글 고유명사는 여기가 아니라 search_items로 찾아야 한다.

        :param keyword: 테이블 이름에 포함될 것으로 예상되는 검색어 (보통 영문 카테고리명)
        """
        con = self._connect()
        try:
            rows = con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND lower(name) LIKE ? ORDER BY name",
                (f"%{keyword.lower()}%",),
            ).fetchall()
        finally:
            con.close()
        return json.dumps([r[0] for r in rows], ensure_ascii=False)

    def get_table_schema(self, table_name: str) -> str:
        """
        지정한 테이블의 CREATE TABLE 구문(정확한 컬럼명/타입)과 샘플 행 3개를 반환한다.
        run_sql로 쿼리를 작성하기 전에 반드시 이 함수로 컬럼명을 확인해야 한다.

        :param table_name: 스키마를 확인할 정확한 테이블 이름 (find_tables/list_categories 결과 중 하나)
        """
        con = self._connect()
        try:
            row = con.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            ).fetchone()
            if row is None:
                return json.dumps(
                    {"error": f"table '{table_name}' not found"}, ensure_ascii=False
                )
            cur = con.execute(f'SELECT * FROM "{table_name}" LIMIT 3')
            cols = [d[0] for d in cur.description]
            sample = [dict(zip(cols, r)) for r in cur.fetchall()]
        finally:
            con.close()
        return json.dumps(
            {"create_table": row[0], "sample_rows": sample}, ensure_ascii=False
        )

    def run_sql(self, query: str) -> str:
        """
        SELECT 쿼리를 dho_structured.sqlite3에 실행하고 결과를 JSON으로 반환한다.
        SELECT 문만 허용되며 결과는 최대 max_rows(기본 200)개까지만 반환된다.
        get_table_schema로 정확한 컬럼명을 확인한 뒤에 호출할 것.

        :param query: 실행할 SELECT SQL 쿼리 한 문장
        """
        stripped = query.strip().rstrip(";")
        if not stripped.lower().startswith("select"):
            return json.dumps(
                {"error": "SELECT 문만 실행할 수 있습니다."}, ensure_ascii=False
            )
        con = self._connect()
        try:
            cur = con.execute(
                f"SELECT * FROM ({stripped}) LIMIT {int(self.valves.max_rows)}"
            )
            cols = [d[0] for d in cur.description]
            rows = [_format_row(dict(zip(cols, r))) for r in cur.fetchall()]
        except sqlite3.Error as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
        finally:
            con.close()
        return json.dumps({"row_count": len(rows), "rows": rows}, ensure_ascii=False)
