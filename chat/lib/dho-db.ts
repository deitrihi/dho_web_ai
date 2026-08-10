// PostgreSQL(구조화 데이터가 이관된 서빙 DB)을 조회하는 Text-to-SQL 도구 함수 모음
// (openwebui_tool_dho_sql.py의 6개 함수를 TypeScript로 그대로 포팅, 이후 Postgres로 전환)
import { createOpenAI } from "@ai-sdk/openai";
import { embed } from "ai";
import { Pool, types, type QueryResultRow } from "pg";

const EMBEDDING_MODEL = process.env.OPENAI_EMBEDDING_MODEL ?? "text-embedding-3-small";

// pg는 bigint(int8, COUNT/SUM 등의 기본 반환 타입)를 오버플로 방지 차원에서 기본적으로
// 문자열로 반환한다. run_sql이 임의의 집계 쿼리를 실행할 수 있는데, 문자열로 오면
// formatRow()의 콤마 포맷팅이 안 먹고 LLM의 숫자 연산도 꼬일 수 있다. 이 프로젝트의 값
// 범위(아이템 수/수량 등)는 Number.MAX_SAFE_INTEGER를 넘을 일이 없으므로 전역으로 숫자
// 변환하도록 오버라이드한다.
types.setTypeParser(20 /* int8 */, (val) => parseInt(val, 10));

const MAX_ROWS = Number(process.env.DHO_MAX_ROWS ?? 200);
// get_backlinks 전용: qty로 재정렬하기 전에 넉넉히 가져올 상한 / 정렬 후 최종 반환 상한
// (흔한 재료는 backlink가 수천 건까지 있어 무제한으로 가져오면 응답이 지나치게 커짐).
const RAW_ENTRY_FETCH_CAP = 500;
const ENTRY_OUTPUT_CAP = 50;

let pool: Pool | undefined;
function getPool(): Pool {
  if (!pool) pool = new Pool({ connectionString: process.env.DATABASE_URL });
  return pool;
}

async function query<T extends QueryResultRow = QueryResultRow>(
  sql: string,
  params: unknown[] = []
): Promise<T[]> {
  const result = await getPool().query<T>(sql, params);
  return result.rows;
}

function quoteIdent(identifier: string): string {
  return `"${identifier.replace(/"/g, '""')}"`;
}

// items_search(pg_trgm GIN 인덱스)로 name/title/description/raw_attrs 속성값까지
// 부분일치 검색한다. 트라이그램은 짧은 키워드일수록 정확도가 떨어지므로 3글자 미만은
// 기존과 동일하게 LIKE 방식으로 폴백한다.
const FTS_MIN_LENGTH = 3;

type ItemMatch = { category: string; item_id: number; name: string | null; title: string | null };

async function findMatchingItems(keyword: string, limit: number): Promise<ItemMatch[]> {
  if ([...keyword].length >= FTS_MIN_LENGTH) {
    return query<ItemMatch>(
      `SELECT category, item_id, name, title FROM items_search
       WHERE search_text ILIKE $1
       ORDER BY word_similarity($2, search_text) DESC
       LIMIT $3`,
      [`%${keyword}%`, keyword, limit]
    );
  }
  return query<ItemMatch>(
    `SELECT category, item_id, name, title FROM items_core
     WHERE name ILIKE $1 OR title ILIKE $1 LIMIT $2`,
    [`%${keyword}%`, limit]
  );
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
async function acquisitionInfo(category: string, itemId: number): Promise<Record<string, unknown[]>> {
  const sharedTables = await query<{ table_name: string }>(
    `SELECT table_name FROM information_schema.tables
     WHERE table_schema = 'public' AND (
       table_name LIKE 'item_acquisition_%' OR
       table_name LIKE 'item_transmutation_%' OR
       table_name = 'item_detail_list'
     )`
  );

  const info: Record<string, unknown[]> = {};
  for (const { table_name: table } of sharedTables) {
    const cols = await query<{ column_name: string }>(
      `SELECT column_name FROM information_schema.columns
       WHERE table_schema = 'public' AND table_name = $1`,
      [table]
    );
    const colNames = new Set(cols.map((c) => c.column_name));
    if (!colNames.has("category") || !colNames.has("item_id")) continue;
    const rows = await query(
      `SELECT * FROM ${quoteIdent(table)} WHERE category = $1 AND item_id = $2`,
      [category, itemId]
    );
    if (rows.length > 0) info[table] = rows;
  }
  return info;
}

export async function listCategories(): Promise<{ category: string; count: number }[]> {
  return query<{ category: string; count: number }>(
    "SELECT category, COUNT(*)::int as count FROM items_core GROUP BY category ORDER BY category"
  );
}

export async function getItemDetail(keyword: string): Promise<unknown[]> {
  const matches = await findMatchingItems(keyword, 10);

  return Promise.all(
    matches.map(async (m) => {
      const entry: Record<string, unknown> = { ...m };
      const descRows = await query<{ description: string | null }>(
        "SELECT description FROM items_core WHERE category = $1 AND item_id = $2",
        [m.category, m.item_id]
      );
      if (descRows[0]) entry.description = descRows[0].description;

      const tableExists = await query(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = $1",
        [m.category]
      );
      if (tableExists.length > 0) {
        const rows = await query(
          `SELECT * FROM ${quoteIdent(m.category)} WHERE item_id = $1`,
          [m.item_id]
        );
        if (rows[0]) entry.detail = rows[0];
      }
      const acquisition = await acquisitionInfo(m.category, m.item_id);
      if (Object.keys(acquisition).length > 0) entry["획득_방법"] = acquisition;
      return entry;
    })
  );
}

export async function searchItems(keyword: string): Promise<unknown[]> {
  return findMatchingItems(keyword, 30);
}

// 요청 처리 시점(런타임)에 process.env를 읽어야 한다 — route.ts의 createOpenAI() 호출과
// 동일한 이유(모듈 최상단에서 만들면 Next.js가 빌드 타임 값을 인라인해버림).
async function embedQuery(text: string): Promise<number[]> {
  const openai = createOpenAI({
    baseURL: process.env.OPENAI_API_BASE_URL,
    apiKey: process.env.OPENAI_API_KEY,
  });
  const { embedding } = await embed({
    model: openai.textEmbeddingModel(EMBEDDING_MODEL),
    value: text,
  });
  return embedding;
}

function vectorLiteral(vec: number[]): string {
  return `[${vec.join(",")}]`;
}

type SemanticMatch = {
  category: string;
  item_id: number;
  name: string | null;
  title: string | null;
  similarity: number;
};

// build_embeddings.py가 만든 item_embeddings(pgvector)에서 코사인 유사도로 가장 가까운
// 아이템을 찾는다. 정확한 이름을 모르거나 "~용도의 아이템", "~한 효과를 가진 스킬"처럼
// 개념/느낌으로 찾을 때 search_items/get_item_detail(정확한 이름 매칭)보다 유리하다.
export async function semanticSearchItems(text: string, limit = 10): Promise<SemanticMatch[]> {
  const embedding = await embedQuery(text);
  return query<SemanticMatch>(
    `SELECT ie.category, ie.item_id, ic.name, ic.title,
            1 - (ie.embedding <=> $1::vector) AS similarity
     FROM item_embeddings ie
     JOIN items_core ic ON ic.category = ie.category AND ic.item_id = ie.item_id
     ORDER BY ie.embedding <=> $1::vector
     LIMIT $2`,
    [vectorLiteral(embedding), limit]
  );
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
async function attachQuantities(
  sourceCategory: string,
  sourceLabel: string,
  entries: { source_item_id: number; name: string | null; title: string | null; source_label: string }[],
  target: { category: string; item_id: number }
): Promise<((typeof entries)[number] & { qty: number | null })[]> {
  const ids = [...new Set(entries.map((e) => e.source_item_id))];
  const tables = ids.length
    ? await query<{ item_id: number; rows_json: string }>(
        `SELECT item_id, rows_json FROM raw_tables
         WHERE category = $1 AND label = $2 AND item_id = ANY($3::int[])`,
        [sourceCategory, sourceLabel, ids]
      )
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
export async function getBacklinks(keyword: string): Promise<unknown[]> {
  const matches = await findMatchingItems(keyword, 10);

  return Promise.all(
    matches.map(async (m) => {
      const bySource = await query<{ source_category: string; count: number }>(
        `SELECT source_category, COUNT(*)::int as count FROM item_backlinks
         WHERE target_category = $1 AND target_item_id = $2
         GROUP BY source_category ORDER BY count DESC`,
        [m.category, m.item_id]
      );

      const backlinks = await Promise.all(
        bySource.map(async (g) => {
          const rawEntries = await query<{
            source_item_id: number;
            name: string | null;
            title: string | null;
            source_label: string;
          }>(
            `SELECT b.source_item_id, ic.name, ic.title, b.source_label FROM item_backlinks b
             JOIN items_core ic ON ic.category = b.source_category AND ic.item_id = b.source_item_id
             WHERE b.target_category = $1 AND b.target_item_id = $2 AND b.source_category = $3
             -- 수량(qty)순으로 최종 정렬해서 상위 ENTRY_OUTPUT_CAP개를 뽑아야 하므로,
             -- SQL 단계에서는 정렬 기준(qty)을 아직 몰라 source_item_id 순으로 넉넉히
             -- 가져온 뒤(RAW_ENTRY_FETCH_CAP) 아래에서 qty로 재정렬한다.
             ORDER BY b.source_item_id LIMIT $4`,
            [m.category, m.item_id, g.source_category, RAW_ENTRY_FETCH_CAP]
          );

          const byLabel = new Map<string, typeof rawEntries>();
          for (const e of rawEntries) {
            const list = byLabel.get(e.source_label) ?? [];
            list.push(e);
            byLabel.set(e.source_label, list);
          }
          const grouped = await Promise.all(
            [...byLabel.entries()].map(([label, list]) =>
              attachQuantities(g.source_category, label, list, {
                category: m.category,
                item_id: m.item_id,
              })
            )
          );
          const entries = grouped
            .flat()
            // qty가 있으면 큰 순서로("가장 많이 주는" 류 질문에 바로 답할 수 있게), qty가
            // 없는 항목(수량 개념이 없는 링크)은 뒤로 보낸다.
            .sort((a, b) => (b.qty ?? -1) - (a.qty ?? -1))
            .slice(0, ENTRY_OUTPUT_CAP);

          return { source_category: g.source_category, count: g.count, entries };
        })
      );

      return { category: m.category, item_id: m.item_id, name: m.name, title: m.title, backlinks };
    })
  );
}

export async function findTables(keyword: string): Promise<string[]> {
  const rows = await query<{ table_name: string }>(
    `SELECT table_name FROM information_schema.tables
     WHERE table_schema = 'public' AND lower(table_name) LIKE $1 ORDER BY table_name`,
    [`%${keyword.toLowerCase()}%`]
  );
  return rows.map((r) => r.table_name);
}

export async function getTableSchema(
  tableName: string
): Promise<{ create_table: string; sample_rows: unknown[] } | { error: string }> {
  const cols = await query<{ column_name: string; data_type: string; is_nullable: "YES" | "NO" }>(
    `SELECT column_name, data_type, is_nullable FROM information_schema.columns
     WHERE table_schema = 'public' AND table_name = $1 ORDER BY ordinal_position`,
    [tableName]
  );
  if (cols.length === 0) return { error: `table '${tableName}' not found` };

  // Postgres엔 SQLite의 sqlite_master.sql 같은 원본 CREATE TABLE 텍스트가 없어서
  // information_schema.columns로부터 동등한 형태를 재구성한다.
  const columnLines = cols.map(
    (c) => `  ${quoteIdent(c.column_name)} ${c.data_type}${c.is_nullable === "NO" ? " NOT NULL" : ""}`
  );
  const create_table = `CREATE TABLE ${quoteIdent(tableName)} (\n${columnLines.join(",\n")}\n)`;
  const sample_rows = await query(`SELECT * FROM ${quoteIdent(tableName)} LIMIT 3`);
  return { create_table, sample_rows };
}

export async function runSql(
  sqlText: string
): Promise<{ row_count: number; rows: unknown[] } | { error: string }> {
  const stripped = sqlText.trim().replace(/;+$/, "");
  if (!stripped.toLowerCase().startsWith("select")) {
    return { error: "SELECT 문만 실행할 수 있습니다." };
  }
  try {
    const rows = await query(`SELECT * FROM (${stripped}) AS sub LIMIT $1`, [MAX_ROWS]);
    return { row_count: rows.length, rows: rows.map((r) => formatRow(r as Record<string, unknown>)) };
  } catch (e) {
    return { error: e instanceof Error ? e.message : String(e) };
  }
}
