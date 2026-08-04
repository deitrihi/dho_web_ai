// 챗봇 서버 에러를 JSONL 파일에 기록하고 조회하는 로거 (/logs 페이지에서 사용)
import fs from "node:fs";
import path from "node:path";

const LOG_PATH =
  process.env.DHO_CHAT_LOG_PATH ??
  path.join(/*turbopackIgnore: true*/ process.cwd(), ".data", "errors.jsonl");

export type ErrorLogEntry = {
  timestamp: string;
  message: string;
  stack?: string[];
  context?: Record<string, unknown>;
};

export function logError(error: unknown, context?: Record<string, unknown>): void {
  const entry: ErrorLogEntry = {
    timestamp: new Date().toISOString(),
    message: error instanceof Error ? error.message : String(error),
    stack: error instanceof Error && error.stack ? error.stack.split("\n") : undefined,
    context,
  };
  console.error(`[chat] ${entry.message}`, error);
  try {
    fs.mkdirSync(path.dirname(LOG_PATH), { recursive: true });
    fs.appendFileSync(LOG_PATH, JSON.stringify(entry) + "\n");
  } catch (writeError) {
    console.error("[chat] 에러 로그 파일 기록 실패:", writeError);
  }
}

export function readErrorLogs(limit = 200): ErrorLogEntry[] {
  if (!fs.existsSync(LOG_PATH)) return [];
  const lines = fs
    .readFileSync(LOG_PATH, "utf-8")
    .split("\n")
    .filter((line) => line.trim().length > 0);
  return lines
    .slice(-limit)
    .reverse()
    .map((line) => {
      try {
        return JSON.parse(line) as ErrorLogEntry;
      } catch {
        return { timestamp: "", message: line };
      }
    });
}
