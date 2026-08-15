// DHO 아카이브 Text-to-SQL 챗봇 API 라우트 (openwebui_tool_dho_sql.py 대체)
import { createOpenAI } from "@ai-sdk/openai";
import {
  convertToModelMessages,
  createUIMessageStream,
  createUIMessageStreamResponse,
  stepCountIs,
  streamText,
  tool,
  toUIMessageStream,
  type UIMessage,
} from "ai";
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
  semanticSearchWiki,
} from "@/lib/dho-db";
import { logError } from "@/lib/error-log";

export const runtime = "nodejs"; // lib/dho-db.ts가 pg(TCP 소켓)를 쓰므로 Edge 런타임 불가
export const maxDuration = 60;

// 1단계(실행) 모델: gpt-5-mini가 도구를 직접 호출해서 DB/위키 원본 자료를 모은다.
// 최종 답변 작성은 2단계(deepseek) 몫이므로, 여기서는 "자료 수집" 역할만 명시하고
// 마지막에 답변 대신 짧은 완료 문구만 남기도록 지시한다(비싼 모델의 출력 토큰을
// 최소화하고, 그 완료 문구가 질문 직후 첫 진행 상황 표시로도 쓰이게 함).
const EXECUTION_SYSTEM_PROMPT = `당신은 대항해시대 온라인 DB 아카이브(PostgreSQL)를 자연어
질문에 맞춰 탐색·조회하는 "자료 수집" 담당입니다. 최종 답변 작성은 다른 모델이 맡으므로,
당신은 답변에 필요한 원본 자료를 도구로 전부 모으는 역할만 합니다.

질문에 아이템/직업/스킬 등 고유명사가 있으면 get_item_detail로 이름 하나로 상세정보를 한 번에
조회하세요. 그걸로 부족하면(관련 하위 테이블 조회, 조건별 집계 등) list_categories -> find_tables
-> get_table_schema -> run_sql 순서로 세부 조회하세요.

도구 호출 횟수는 제한되어 있습니다(한 대화 턴당 최대 스텝 수). 같은 키워드로 여러 도구를
중복 호출하지 마세요 — 예를 들어 get_item_detail로 이미 찾은 아이템을 search_items로 다시
찾거나, semantic_search_items로 이미 찾은 걸 get_item_detail로 또 찾는 식의 재확인은
낭비입니다. 특히 재료/구매처처럼 여러 항목을 한 번에 조사해야 하는 질문(예: "A를 만드는
재료들을 각각 어디서 사나")에서는 항목마다 get_item_detail을 딱 한 번만 부르고, 그 결과의
"획득_방법" 필드에서 구매처/판매 NPC 정보를 바로 읽으세요 — search_items로 재확인할
필요가 없습니다(search_items는 상세정보가 없어 이런 질문엔 애초에 도움이 안 됩니다).

정확한 이름을 모르거나 "~용도로 쓰는 아이템", "~한 효과를 가진 스킬"처럼 개념/느낌으로 찾는
질문에는 semantic_search_items를 쓰세요. search_items/get_item_detail은 이름이 정확히
포함되어야 찾지만, semantic_search_items는 의미가 비슷한 항목을 찾아줍니다.

get_item_detail 결과의 "획득_방법" 필드에는 판매 NPC/퀘스트/해상 NPC/레시피/변성연금 등 공유
테이블에서 찾은 이 아이템의 실제 획득 경로가 전부 들어있습니다 — "이 아이템 어디서 구하나"
질문은 여기만 보면 됩니다.

"이 아이템을 보상으로 주는 퀘스트", "이 재료를 쓰는 레시피" 처럼 반대로 "어떤 항목이 이걸
참조/포함하는가"를 묻는 질문(역방향)은 get_item_detail이 아니라 get_backlinks를 바로
쓰세요. item_acquisition_*/item_detail_list를 find_tables·get_table_schema로 직접
탐색하며 역방향 관계를 추측하지 마세요 — 이미 인덱싱된 get_backlinks가 훨씬 빠릅니다.

run_sql로 쿼리를 작성하기 전에는 반드시 get_table_schema로 정확한 컬럼명을 먼저 확인하세요.
run_sql은 SELECT 문만 허용됩니다.

semantic_search_wiki는 DHO 위키(사람이 직접 편집한 설명/가이드 포함)에서 개념/느낌으로
관련 내용을 찾습니다. 위 도구들로 답을 못 찾았거나 "어떻게 공략하나", "왜 이런 효과가
있나" 처럼 설명형 질문일 때 보완적으로 쓰세요. 질문 주제와 관련된 위키 문서는 최대한
넉넉히 모으세요(limit을 늘려서 여러 번 호출해도 됨) — 어떤 내용을 답변에 쓸지는 다음
단계(답변 작성 모델)가 고릅니다.

호출 한도에 가까워지면 지금까지 모은 자료로 충분한지 판단하고 멈추세요. 자료 수집을
마쳤으면 답변을 직접 쓰지 말고 "자료 수집을 마쳤습니다."라고만 짧게 답하세요 — 최종 답변은
다음 단계 모델이 작성합니다.`;

// 2단계(정리) 모델: deepseek-v4-flash가 도구 없이, 1단계가 모은 원본 자료(system 뒤에
// 첨부)만 근거로 최종 답변을 작성한다. 도구를 직접 호출한 적이 없으므로 자료 해석 규칙을
// 명시해줘야 한다(원래 실행 모델이 알아서 판단하던 것들 — qty 정렬, similarity 필터링,
// wiki grounded_item 우선순위 등).
const SYNTHESIS_SYSTEM_PROMPT = `당신은 대항해시대 온라인 DB 아카이브 챗봇의 "최종 답변 작성"
담당입니다. 다른 모델이 도구로 미리 수집한 원본 자료(DB 조회 결과 + 위키 문서)가 이 system
메시지 뒤에 첨부되어 있습니다. 당신은 도구를 직접 호출할 수 없으니 첨부된 자료만 근거로
답변하세요 — 자료에 없는 내용은 추측하지 말고 못 찾았다고 답하세요.

자료 해석 규칙.
- get_item_detail 결과의 "획득_방법" 필드가 이 아이템을 어디서/어떻게 얻는지에 대한 정답입니다.
- get_backlinks 결과의 entries는 이미 qty(수량) 내림차순 정렬되어 있습니다 — "가장 많이
  주는 퀘스트" 같은 질문은 재정렬 없이 앞쪽만 그대로 쓰면 됩니다. qty가 null인 항목은
  수량 개념이 없는 링크입니다.
- semantic_search_items/semantic_search_wiki 결과의 similarity(0~1, 높을수록 유사)가
  낮은 항목(대략 0.3 미만)은 관련 없을 수 있으니 걸러서 판단하세요.
- semantic_search_wiki 결과에 grounded_item(DB 원본 레코드)이 있으면 사실 근거는 반드시
  grounded_item을 우선하고 chunk_text는 참고 설명으로만 쓰세요 — Wiki 텍스트 자체를 사실
  근거로 인용하지 마세요(사람이 편집해서 오래되거나 틀릴 수 있음). grounded_item이 null인
  결과(자유 위키 페이지)만 chunk_text 자체를 근거로 써도 됩니다.

답변은 한국어로, 표/목록을 활용해서 필요한 만큼 충분히 상세하게 정리해서 답하세요.`;

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

// 1단계(execution)가 모은 도구 호출 결과를 2단계(synthesis)의 system 프롬프트에 그대로
// 첨부할 수 있는 텍스트 블록으로 직렬화한다.
function formatGatheredData(
  toolResults: { toolName: string; input: unknown; output: unknown }[]
): string {
  if (toolResults.length === 0) return "(수집된 자료 없음)";
  return toolResults
    .map(
      (r, i) =>
        `### ${i + 1}. ${r.toolName}(${JSON.stringify(r.input)})\n${JSON.stringify(r.output, null, 2)}`
    )
    .join("\n\n");
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
  // DeepSeek API는 OpenAI 호환(https://api.deepseek.com)이라 별도 SDK 없이 createOpenAI를
  // baseURL만 바꿔 재사용한다.
  const deepseek = createOpenAI({
    baseURL: process.env.DEEPSEEK_API_BASE_URL ?? "https://api.deepseek.com",
    apiKey: process.env.DEEPSEEK_API_KEY,
  });

  const tools = {
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
        "get_item_detail을 바로 호출하는 게 낫다. 이미 같은 키워드로 get_item_detail을 " +
        "불렀다면 이 도구를 다시 부르지 말 것 — 얻는 정보가 겹치지 않고 호출만 낭비된다.",
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
    semantic_search_wiki: tool({
      description:
        "DHO 위키(Wiki.js, 사람이 직접 편집 가능한 설명/가이드 문서 포함)에서 자연어 " +
        "질문과 의미가 비슷한 내용을 벡터 검색으로 찾는다. 결과의 grounded_item이 있으면 " +
        "그게 이 청크가 속한 아이템의 DB 원본 레코드다 — 최종 답변의 사실 근거는 항상 " +
        "grounded_item을 우선하고 chunk_text는 보조 설명으로만 참고한다.",
      inputSchema: z.object({
        text: z.string().describe("찾고 싶은 내용을 설명하는 자연어 문장/구절"),
        limit: z.number().int().min(1).max(20).optional().describe("반환할 최대 개수 (기본 5)"),
      }),
      execute: async ({ text, limit }) => semanticSearchWiki(text, limit),
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
  };

  // 1단계(gpt-5-mini, 도구 실행)와 2단계(deepseek, 최종 답변)를 하나의 응답 스트림으로
  // 합친다. 1단계 도구 호출이 질문 직후부터 실시간으로 화면에 뜨고, 끝나는 대로 같은
  // 말풍선에 2단계 답변이 이어서 스트리밍된다 — 전체가 끝날 때까지 기다렸다 한 번에
  // 보내는 것보다 체감 대기시간이 짧다.
  const stream = createUIMessageStream({
    execute: async ({ writer }) => {
      // 1단계(실행): gpt-5-mini가 실제 도구 호출로 DB/위키 원본 자료를 수집한다.
      const execution = streamText({
        model: openai(process.env.OPENAI_MODEL ?? "gpt-5-mini"),
        system: EXECUTION_SYSTEM_PROMPT,
        messages: modelMessages,
        // 재료 여러 개의 구매처를 한 번에 조사하는 질문처럼 항목당 도구 호출이 여러 번
        // 필요한 복합 질문에 여유를 주기 위해 16 -> 24로 상향(중복 호출 방지 규칙과 함께 적용).
        stopWhen: stepCountIs(24),
        onError: ({ error }) => logError(error, { route: "/api/chat", phase: "execution" }),
        tools,
      });
      // sendFinish: false — 이어서 2단계 텍스트가 같은 메시지에 붙을 것이므로 여기서
      // 메시지를 끝내지 않는다.
      writer.merge(toUIMessageStream({ stream: execution.fullStream, tools, sendFinish: false }));

      const toolResults = await execution.toolResults;
      const gatheredData = formatGatheredData(toolResults);

      // 2단계(정리): deepseek-v4-flash가 도구 없이, 수집된 원본 자료만으로 최종 답변을 작성한다.
      const synthesis = streamText({
        model: deepseek(process.env.DEEPSEEK_MODEL ?? "deepseek-v4-flash"),
        system: `${SYNTHESIS_SYSTEM_PROMPT}\n\n## 1단계에서 수집한 원본 자료\n${gatheredData}`,
        messages: modelMessages,
        onError: ({ error }) => logError(error, { route: "/api/chat", phase: "synthesis" }),
      });
      // sendStart: false — 1단계와 같은 메시지의 연속으로 이어붙인다.
      writer.merge(toUIMessageStream({ stream: synthesis.fullStream, sendStart: false }));
    },
    onError: () => "서버 에러가 발생했습니다.",
  });

  return createUIMessageStreamResponse({ stream });
}
