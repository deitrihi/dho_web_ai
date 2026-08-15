// 챗봇 서버 에러 로그 조회 페이지 (.data/errors.jsonl 또는 DHO_CHAT_LOG_PATH 파일을 읽어 표시)
import { readErrorLogs } from "@/lib/error-log";
import { JsonValue } from "../components/rich-content";

export const dynamic = "force-dynamic";

const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

export default function LogsPage() {
  const logs = readErrorLogs();

  return (
    <div className="flex-grow-1 bg-body text-body p-3">
      <header className="mb-3 d-flex align-items-center justify-content-between">
        <div>
          <h1 className="fs-6 fw-bold mb-0">챗봇 서버 에러 로그</h1>
          <p className="small text-body-secondary mb-0">
            최근 {logs.length}건 (최신순) — 새로고침하면 다시 조회합니다
          </p>
        </div>
        <a href={`${basePath}/`} className="small">
          챗봇으로 돌아가기
        </a>
      </header>

      {logs.length === 0 ? (
        <p className="small text-body-secondary">기록된 에러가 없습니다.</p>
      ) : (
        <div className="rounded border bg-body-tertiary p-2 small">
          <JsonValue value={logs} />
        </div>
      )}
    </div>
  );
}
