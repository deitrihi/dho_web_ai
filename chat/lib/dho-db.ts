// dho_structured.sqlite3를 읽기 전용으로 조회하는 Text-to-SQL 도구 함수 모음
// (openwebui_tool_dho_sql.py의 6개 함수를 TypeScript로 그대로 포팅)
import path from "node:path";
import { DatabaseSync } from "node:sqlite";

const DB_PATH =
  process.env.DHO_DB_PATH ?? path.join(process.cwd(), "..", "dho_structured.sqlite3");
const MAX_ROWS = Number(process.env.DHO_MAX_ROWS ?? 200);

function connect(): DatabaseSync {
  return new DatabaseSync(DB_PATH, { readOnly: true, open: true });
}

// item_acquisition_*/item_transmutation_*/item_detail_list 공유 테이블에서 이 아이템의
// 획득처/변성연금 정보를 전부 모아 온다. 이 테이블들은 카테고리 전용 테이블(예: certificate)과
// 별도로 존재해서, item_id로 직접 조인하지 않으면 검색에서 누락되기 쉽다.
function acquisitionInfo(
  db: DatabaseSync,
  category: string,
  itemId: number
): Record<string, unknown[]> {
  const sharedTables = db
    .prepare(
      "SELECT name FROM sqlite_master WHERE type='table' AND " +
        "(name LIKE 'item_acquisition_%' OR name LIKE 'item_transmutation_%' " +
        "OR name = 'item_detail_list')"
    )
    .all() as { name: string }[];

  const info: Record<string, unknown[]> = {};
  for (const { name: table } of sharedTables) {
    const cols = new Set(
      (db.prepare(`PRAGMA table_info("${table}")`).all() as { name: string }[]).map(
        (r) => r.name
      )
    );
    if (!cols.has("category") || !cols.has("item_id")) continue;
    const rows = db
      .prepare(`SELECT * FROM "${table}" WHERE category = ? AND item_id = ?`)
      .all(category, itemId);
    if (rows.length > 0) info[table] = rows;
  }
  return info;
}

export function listCategories(): { category: string; count: number }[] {
  const db = connect();
  try {
    return db
      .prepare("SELECT category, COUNT(*) as count FROM items_core GROUP BY category ORDER BY category")
      .all() as { category: string; count: number }[];
  } finally {
    db.close();
  }
}

export function getItemDetail(keyword: string): unknown[] {
  const db = connect();
  try {
    const matches = db
      .prepare(
        "SELECT category, item_id, name, title, description FROM items_core " +
          "WHERE name LIKE ? OR title LIKE ? LIMIT 10"
      )
      .all(`%${keyword}%`, `%${keyword}%`) as {
      category: string;
      item_id: number;
      name: string | null;
      title: string | null;
      description: string | null;
    }[];

    return matches.map((m) => {
      const entry: Record<string, unknown> = { ...m };
      const tableExists = db
        .prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?")
        .get(m.category);
      if (tableExists) {
        const row = db
          .prepare(`SELECT * FROM "${m.category}" WHERE item_id = ?`)
          .get(m.item_id);
        if (row) entry.detail = row;
      }
      const acquisition = acquisitionInfo(db, m.category, m.item_id);
      if (Object.keys(acquisition).length > 0) entry["획득_방법"] = acquisition;
      return entry;
    });
  } finally {
    db.close();
  }
}

export function searchItems(keyword: string): unknown[] {
  const db = connect();
  try {
    return db
      .prepare(
        "SELECT category, item_id, name, title FROM items_core " +
          "WHERE name LIKE ? OR title LIKE ? LIMIT 30"
      )
      .all(`%${keyword}%`, `%${keyword}%`);
  } finally {
    db.close();
  }
}

export function findTables(keyword: string): string[] {
  const db = connect();
  try {
    const rows = db
      .prepare(
        "SELECT name FROM sqlite_master WHERE type='table' AND lower(name) LIKE ? ORDER BY name"
      )
      .all(`%${keyword.toLowerCase()}%`) as { name: string }[];
    return rows.map((r) => r.name);
  } finally {
    db.close();
  }
}

export function getTableSchema(tableName: string): { create_table: string; sample_rows: unknown[] } | { error: string } {
  const db = connect();
  try {
    const row = db
      .prepare("SELECT sql FROM sqlite_master WHERE type='table' AND name=?")
      .get(tableName) as { sql: string } | undefined;
    if (!row) return { error: `table '${tableName}' not found` };
    const sample = db.prepare(`SELECT * FROM "${tableName}" LIMIT 3`).all();
    return { create_table: row.sql, sample_rows: sample };
  } finally {
    db.close();
  }
}

export function runSql(query: string): { row_count: number; rows: unknown[] } | { error: string } {
  const stripped = query.trim().replace(/;+$/, "");
  if (!stripped.toLowerCase().startsWith("select")) {
    return { error: "SELECT 문만 실행할 수 있습니다." };
  }
  const db = connect();
  try {
    const rows = db.prepare(`SELECT * FROM (${stripped}) LIMIT ${MAX_ROWS}`).all();
    return { row_count: rows.length, rows };
  } catch (e) {
    return { error: e instanceof Error ? e.message : String(e) };
  } finally {
    db.close();
  }
}
