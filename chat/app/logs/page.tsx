// 챗봇 서버 에러 로그 조회 페이지 (.data/errors.jsonl 또는 DHO_CHAT_LOG_PATH 파일을 읽어 표시)
import { readErrorLogs } from "@/lib/error-log";
import { JsonValue } from "../components/rich-content";

export const dynamic = "force-dynamic";

const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

export default function LogsPage() {
  const logs = readErrorLogs();

  return (
    <div className="min-h-dvh bg-neutral-950 p-4 text-neutral-100">
      <header className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-sm font-bold">챗봇 서버 에러 로그</h1>
          <p className="text-xs text-neutral-500">
            최근 {logs.length}건 (최신순) — 새로고침하면 다시 조회합니다
          </p>
        </div>
        <a href={`${basePath}/`} className="text-xs text-blue-400 underline">
          챗봇으로 돌아가기
        </a>
      </header>

      {logs.length === 0 ? (
        <p className="text-sm text-neutral-500">기록된 에러가 없습니다.</p>
      ) : (
        <div className="rounded border border-neutral-800 bg-neutral-900 p-2 text-xs">
          <JsonValue value={logs} />
        </div>
      )}
    </div>
  );
}
