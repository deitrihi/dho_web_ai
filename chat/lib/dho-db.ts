// dho_structured.sqlite3를 읽기 전용으로 조회하는 Text-to-SQL 도구 함수 모음
// (openwebui_tool_dho_sql.py의 6개 함수를 TypeScript로 그대로 포팅)
import path from "node:path";
import { DatabaseSync } from "node:sqlite";

const DB_PATH =
  process.env.DHO_DB_PATH ?? path.join(process.cwd(), "..", "dho_structured.sqlite3");
const MAX_ROWS = Number(process.env.DHO_MAX_ROWS ?? 200);
// get_backlinks 전용: qty로 재정렬하기 전에 넉넉히 가져올 상한 / 정렬 후 최종 반환 상한
// (흔한 재료는 backlink가 수천 건까지 있어 무제한으로 가져오면 응답이 지나치게 커짐).
const RAW_ENTRY_FETCH_CAP = 500;
const ENTRY_OUTPUT_CAP = 50;

function connect(): DatabaseSync {
  return new DatabaseSync(DB_PATH, { readOnly: true, open: true });
}

// items_fts(FTS5, trigram 토크나이저)로 name/title/description/raw_attrs 속성값까지
// 부분일치 검색한다. trigram은 3글자 미만은 인덱싱하지 않으므로(SQLite 제약) 그보다
// 짧은 키워드는 기존 LIKE 방식으로 폴백한다.
const FTS_MIN_LENGTH = 3;

// MATCH에 넘기는 키워드를 큰따옴표로 감싸 "구문(phrase)" 검색으로 강제한다 — 안 그러면
// 공백이 AND로 쪼개지거나(예: "조합 등록" -> 조합 AND 등록) AND/OR 같은 FTS5 예약어가
// 든 키워드가 검색 문법으로 해석돼버린다.
function ftsPhrase(keyword: string): string {
  return `"${keyword.replace(/"/g, '""')}"`;
}

type ItemMatch = { category: string; item_id: number; name: string | null; title: string | null };

function findMatchingItems(db: DatabaseSync, keyword: string, limit: number): ItemMatch[] {
  if ([...keyword].length >= FTS_MIN_LENGTH) {
    return db
      .prepare(
        `SELECT category, item_id, name, title FROM items_fts ` +
          `WHERE items_fts MATCH ? ORDER BY bm25(items_fts) LIMIT ${limit}`
      )
      .all(ftsPhrase(keyword)) as ItemMatch[];
  }
  return db
    .prepare(
      `SELECT category, item_id, name, title FROM items_core ` +
        `WHERE name LIKE ? OR title LIKE ? LIMIT ${limit}`
    )
    .all(`%${keyword}%`, `%${keyword}%`) as ItemMatch[];
}

// item_id/row_index/position이나 "{라벨}_id" 외래키 컬럼은 수량이 아니라 식별자라서
// 콤마를 붙이면 "12,345" 같은 값처럼 오해할 수 있다 -> formatNumber 대상에서 제외한다.
const ID_LIKE_NAMES = new Set(["item_id", "row_index", "position"]);

// 숫자 값을 세자리마다 콤마를 넣은 문자열로 바꾼다. 숫자가 아니면 그대로 반환한다.
function formatNumber(value: unknown): unknown {
  return typeof value === "number" ? value.toLocaleString("en-US") : value;
}

function formatRow(row: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(row).map(([k, v]) => [
      k,
      ID_LIKE_NAMES.has(k) || k.endsWith("_id") ? v : formatNumber(v),
    ])
  );
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
    const matches = findMatchingItems(db, keyword, 10);

    return matches.map((m) => {
      const entry: Record<string, unknown> = { ...m };
      const descRow = db
        .prepare("SELECT description FROM items_core WHERE category = ? AND item_id = ?")
        .get(m.category, m.item_id) as { description: string | null } | undefined;
      if (descRow) entry.description = descRow.description;
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
    return findMatchingItems(db, keyword, 30);
  } finally {
    db.close();
  }
}

type RawLink = { category: string; item_id: number; text: string };
type RawCell = { text: string; links: RawLink[] };

// raw_tables 셀 텍스트("구입 발주서(카테고리 1) 5")에서 링크 자체의 표시 텍스트
// ("구입 발주서(카테고리 1)")를 뺀 나머지가 숫자만 남으면 그게 수량이다. 링크 텍스트가
// 앞부분과 정확히 일치하지 않거나(레이아웃이 다른 경우) 남는 텍스트가 숫자가 아니면
// 수량이 명시되지 않은 것으로 보고 null을 반환한다.
function extractQuantity(cellText: string, linkText: string): number | null {
  if (!cellText.startsWith(linkText)) return null;
  const suffix = cellText.slice(linkText.length).trim();
  return /^\d+$/.test(suffix) ? Number(suffix) : null;
}

// item_backlinks는 "누가 참조하는가"만 알려주고 수량은 없다(애초에 그런 개념이 없는
// 링크도 섞여 있어서). "종류/내용"(필요/보상 등) 표에서 온 backlink는 원본 raw_tables
// 셀 텍스트에 수량이 그대로 남아있으므로, 같은 (category,item_id,label) 키로 raw_tables를
// 찾아 대상 아이템 링크가 있는 셀에서 수량을 뽑아 entries에 붙여준다.
function attachQuantities(
  db: DatabaseSync,
  sourceCategory: string,
  sourceLabel: string,
  entries: { source_item_id: number; name: string | null; title: string | null; source_label: string }[],
  target: { category: string; item_id: number }
): ((typeof entries)[number] & { qty: number | null })[] {
  const ids = [...new Set(entries.map((e) => e.source_item_id))];
  const placeholders = ids.map(() => "?").join(",");
  const tables = ids.length
    ? (db
        .prepare(
          `SELECT item_id, rows_json FROM raw_tables WHERE category = ? AND label = ? AND item_id IN (${placeholders})`
        )
        .all(sourceCategory, sourceLabel, ...ids) as { item_id: number; rows_json: string }[])
    : [];

  const qtyByItem = new Map<number, number>();
  for (const { item_id, rows_json } of tables) {
    if (qtyByItem.has(item_id)) continue;
    const rows = JSON.parse(rows_json) as RawCell[][];
    findQty: for (const row of rows) {
      for (const cell of row) {
        const link = cell.links.find(
          (l) => l.category === target.category && l.item_id === target.item_id
        );
        if (!link) continue;
        const qty = extractQuantity(cell.text, link.text);
        if (qty !== null) {
          qtyByItem.set(item_id, qty);
          break findQty;
        }
      }
    }
  }

  return entries.map((e) => ({ ...e, qty: qtyByItem.get(e.source_item_id) ?? null }));
}

// 이 아이템/조건을 다른 항목이 참조하는 곳(역방향 링크)을 찾는다 — 웹앱 상세 페이지의
// "이 항목을 참조하는 곳" 섹션과 같은 데이터(item_backlinks). "이 아이템을 보상으로 주는
// 퀘스트", "이 재료를 쓰는 레시피"처럼 "어떤 항목이 이걸 참조/포함하는가"를 묻는 질문은
// get_item_detail(정방향: 이 항목 자신의 획득처)로는 못 찾고 이 함수로 찾아야 한다.
// entries의 qty는 "종류/내용"(필요/보상 등) 표에서 온 backlink에서만 채워지고, 그 외
// (판매 NPC 목록 등 수량 개념이 없는 링크)는 null이다.
export function getBacklinks(keyword: string): unknown[] {
  const db = connect();
  try {
    const matches = findMatchingItems(db, keyword, 10);

    return matches.map((m) => {
      const bySource = db
        .prepare(
          "SELECT source_category, COUNT(*) as count FROM item_backlinks " +
            "WHERE target_category = ? AND target_item_id = ? " +
            "GROUP BY source_category ORDER BY count DESC"
        )
        .all(m.category, m.item_id) as { source_category: string; count: number }[];

      const backlinks = bySource.map((g) => {
        const rawEntries = db
          .prepare(
            "SELECT b.source_item_id, ic.name, ic.title, b.source_label FROM item_backlinks b " +
              "JOIN items_core ic ON ic.category = b.source_category AND ic.item_id = b.source_item_id " +
              "WHERE b.target_category = ? AND b.target_item_id = ? AND b.source_category = ? " +
              // 수량(qty)순으로 최종 정렬해서 상위 ENTRY_OUTPUT_CAP개를 뽑아야 하므로,
              // SQL 단계에서는 정렬 기준(qty)을 아직 몰라 source_item_id 순으로 넉넉히
              // 가져온 뒤(RAW_ENTRY_FETCH_CAP) 아래에서 qty로 재정렬한다.
              `ORDER BY b.source_item_id LIMIT ${RAW_ENTRY_FETCH_CAP}`
          )
          .all(m.category, m.item_id, g.source_category) as {
          source_item_id: number;
          name: string | null;
          title: string | null;
          source_label: string;
        }[];

        const byLabel = new Map<string, typeof rawEntries>();
        for (const e of rawEntries) {
          const list = byLabel.get(e.source_label) ?? [];
          list.push(e);
          byLabel.set(e.source_label, list);
        }
        const entries = [...byLabel.entries()]
          .flatMap(([label, list]) =>
            attachQuantities(db, g.source_category, label, list, {
              category: m.category,
              item_id: m.item_id,
            })
          )
          // qty가 있으면 큰 순서로("가장 많이 주는" 류 질문에 바로 답할 수 있게), qty가
          // 없는 항목(수량 개념이 없는 링크)은 뒤로 보낸다.
          .sort((a, b) => (b.qty ?? -1) - (a.qty ?? -1))
          .slice(0, ENTRY_OUTPUT_CAP);

        return { source_category: g.source_category, count: g.count, entries };
      });

      return { category: m.category, item_id: m.item_id, name: m.name, title: m.title, backlinks };
    });
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
    return { row_count: rows.length, rows: rows.map((r) => formatRow(r as Record<string, unknown>)) };
  } catch (e) {
    return { error: e instanceof Error ? e.message : String(e) };
  } finally {
    db.close();
  }
}
