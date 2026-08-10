// DHO 아카이브 Text-to-SQL 챗봇 API 라우트 (openwebui_tool_dho_sql.py 대체)
import { createOpenAI } from "@ai-sdk/openai";
import { convertToModelMessages, stepCountIs, streamText, tool, type UIMessage } from "ai";
import { z } from "zod";
import {
  findTables,
  getBacklinks,
  getItemDetail,
  getTableSchema,
  listCategories,
  runSql,
  searchItems,
  semanticSearchItems,
} from "@/lib/dho-db";
import { logError } from "@/lib/error-log";

export const runtime = "nodejs"; // lib/dho-db.ts가 pg(TCP 소켓)를 쓰므로 Edge 런타임 불가
export const maxDuration = 60;

const SYSTEM_PROMPT = `당신은 대항해시대 온라인 DB 아카이브(PostgreSQL)를 자연어 질문에
맞춰 탐색·조회하는 어시스턴트입니다.

질문에 아이템/직업/스킬 등 고유명사가 있으면 get_item_detail로 이름 하나로 상세정보를 한 번에
조회하세요. 그걸로 부족하면(관련 하위 테이블 조회, 조건별 집계 등) list_categories -> find_tables
-> get_table_schema -> run_sql 순서로 세부 조회하세요.

정확한 이름을 모르거나 "~용도로 쓰는 아이템", "~한 효과를 가진 스킬"처럼 개념/느낌으로 찾는
질문에는 semantic_search_items를 쓰세요. search_items/get_item_detail은 이름이 정확히
포함되어야 찾지만, semantic_search_items는 의미가 비슷한 항목을 찾아줍니다. 반환된
similarity(0~1, 높을수록 유사)가 낮은 항목은 관련 없을 수 있으니 걸러서 판단하세요.

get_item_detail 결과의 "획득_방법" 필드에는 판매 NPC/퀘스트/해상 NPC/레시피/변성연금 등 공유
테이블에서 찾은 이 아이템의 실제 획득 경로가 전부 들어있습니다 — "이 아이템 어디서 구하나"
질문은 여기만 보면 됩니다.

"이 아이템을 보상으로 주는 퀘스트", "이 재료를 쓰는 레시피" 처럼 반대로 "어떤 항목이 이걸
참조/포함하는가"를 묻는 질문(역방향)은 get_item_detail이 아니라 get_backlinks를 바로
쓰세요. item_acquisition_*/item_detail_list를 find_tables·get_table_schema로 직접
탐색하며 역방향 관계를 추측하지 마세요 — 이미 인덱싱된 get_backlinks가 훨씬 빠릅니다.

run_sql로 쿼리를 작성하기 전에는 반드시 get_table_schema로 정확한 컬럼명을 먼저 확인하세요.
run_sql은 SELECT 문만 허용됩니다.

답변은 한국어로, 표/목록을 활용해서 간결하게 정리해서 답하세요.`;

export async function POST(req: Request) {
  try {
    return await handleChat(req);
  } catch (error) {
    logError(error, { route: "/api/chat" });
    return new Response(JSON.stringify({ error: "서버 에러가 발생했습니다." }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }
}

async function handleChat(req: Request): Promise<Response> {
  const { messages }: { messages: UIMessage[] } = await req.json();
  const modelMessages = await convertToModelMessages(messages);

  // 요청 처리 시점(런타임)에 process.env를 읽어야 한다. 모듈 최상단에서 생성하면 Next.js
  // 빌드가 process.env.OPENAI_API_BASE_URL을 빌드 타임에 인라인해버려서(빌드 시점엔 이
  // 값이 없었으므로 빈 문자열로 굳어짐), 컨테이너 실행 시 docker-compose가 넣어주는 실제
  // 런타임 환경변수를 무시하고 계속 "baseURL must be a non-empty string" 에러가 난다.
  const openai = createOpenAI({
    baseURL: process.env.OPENAI_API_BASE_URL,
    apiKey: process.env.OPENAI_API_KEY,
  });

  const result = streamText({
    model: openai(process.env.OPENAI_MODEL ?? "gpt-5-mini"),
    system: SYSTEM_PROMPT,
    messages: modelMessages,
    stopWhen: stepCountIs(16),
    onError: ({ error }) => logError(error, { route: "/api/chat", phase: "streaming" }),
    tools: {
      list_categories: tool({
        description:
          "DHO 아카이브 DB에 존재하는 70개 아이템/컨텐츠 카테고리 이름과 카테고리별 항목 수를 " +
          "반환한다. 질문과 관련된 카테고리가 뭔지 모를 때 가장 먼저 호출한다.",
        inputSchema: z.object({}),
        execute: async () => listCategories(),
      }),
      get_item_detail: tool({
        description:
          "아이템/직업/스킬 등 고유명사로 검색해서 해당 항목의 상세 정보를 한 번의 호출로 전부 " +
          "반환한다. 질문에 특정 이름이 나오면 다른 도구보다 이 도구를 가장 먼저 시도한다. " +
          "동명이인처럼 여러 건이 매칭되면 전부 반환하니 그중 질문에 맞는 것을 고르면 된다.",
        inputSchema: z.object({
          keyword: z.string().describe("검색할 아이템/직업/컨텐츠 이름 (전체 또는 일부)"),
        }),
        execute: async ({ keyword }) => getItemDetail(keyword),
      }),
      get_backlinks: tool({
        description:
          "이 아이템/조건을 다른 항목이 참조하는 곳(역방향 링크)을 찾는다 — 출처 카테고리별로 " +
          "개수와 목록을 반환한다. '이 아이템을 보상으로 주는 퀘스트', '이 재료를 쓰는 " +
          "레시피/변성연금', '이 조건이 필요한 퀘스트' 처럼 '어떤 항목이 이걸 참조/포함하는가'를 " +
          "묻는 질문(역방향)에 사용한다. get_item_detail의 '획득_방법'은 반대 방향(이 항목 " +
          "자신을 어디서 얻는지)이라 이런 질문엔 못 쓴다. entries의 qty 필드는 '필요/보상' 같은 " +
          "표에서 이 항목을 몇 개 주고받는지를 담고 있고, entries는 이미 qty 내림차순으로 " +
          "정렬되어 있다 — '가장 많이 주는 퀘스트 10개' 같은 질문은 정렬된 앞쪽만 그대로 " +
          "쓰면 된다(직접 재정렬할 필요 없음). 수량 개념이 없는 링크(예: 판매 NPC 목록)는 " +
          "qty가 null이라 뒤쪽에 온다.",
        inputSchema: z.object({
          keyword: z.string().describe("검색할 아이템/조건 이름 (전체 또는 일부)"),
        }),
        execute: async ({ keyword }) => getBacklinks(keyword),
      }),
      search_items: tool({
        description:
          "아이템/직업/스킬 등 고유명사로 전체 아이템 이름(items_core)을 검색해서 그 이름이 어느 " +
          "category와 item_id에 속하는지만 가볍게 찾는다. 상세 정보까지 필요하면 이 도구 대신 " +
          "get_item_detail을 바로 호출하는 게 낫다.",
        inputSchema: z.object({
          keyword: z.string().describe("검색할 아이템/직업/컨텐츠 이름 (전체 또는 일부)"),
        }),
        execute: async ({ keyword }) => searchItems(keyword),
      }),
      semantic_search_items: tool({
        description:
          "자연어 설명/개념으로 의미가 비슷한 아이템을 벡터 검색으로 찾는다. 정확한 이름을 " +
          "모를 때, 또는 '~용도의 아이템'/'~한 효과' 처럼 느낌으로 찾을 때 search_items 대신 " +
          "이 도구를 쓴다. 결과의 similarity가 낮으면(대략 0.3 미만) 관련 없는 항목일 수 있다.",
        inputSchema: z.object({
          text: z.string().describe("찾고 싶은 대상을 설명하는 자연어 문장/구절"),
          limit: z.number().int().min(1).max(30).optional().describe("반환할 최대 개수 (기본 10)"),
        }),
        execute: async ({ text, limit }) => semanticSearchItems(text, limit),
      }),
      find_tables: tool({
        description:
          "테이블 이름에 keyword가 포함된 테이블 목록을 반환한다(대소문자 무시). " +
          "list_categories에서 찾은 카테고리 이름(영문)으로 검색해서 관련 테이블을 찾을 때 " +
          "사용한다. 질문에 나온 한글 고유명사는 여기가 아니라 search_items로 찾아야 한다.",
        inputSchema: z.object({
          keyword: z.string().describe("테이블 이름에 포함될 것으로 예상되는 검색어 (보통 영문 카테고리명)"),
        }),
        execute: async ({ keyword }) => findTables(keyword),
      }),
      get_table_schema: tool({
        description:
          "지정한 테이블의 CREATE TABLE 구문(정확한 컬럼명/타입)과 샘플 행 3개를 반환한다. " +
          "run_sql로 쿼리를 작성하기 전에 반드시 이 도구로 컬럼명을 확인해야 한다.",
        inputSchema: z.object({
          table_name: z.string().describe("스키마를 확인할 정확한 테이블 이름"),
        }),
        execute: async ({ table_name }) => getTableSchema(table_name),
      }),
      run_sql: tool({
        description:
          "SELECT 쿼리를 PostgreSQL DB에 실행하고 결과를 반환한다. SELECT 문만 " +
          "허용되며 결과는 최대 200개까지만 반환된다. get_table_schema로 정확한 컬럼명을 " +
          "확인한 뒤에 호출할 것.",
        inputSchema: z.object({
          query: z.string().describe("실행할 SELECT SQL 쿼리 한 문장"),
        }),
        execute: async ({ query }) => runSql(query),
      }),
    },
  });

  return result.toUIMessageStreamResponse();
}
