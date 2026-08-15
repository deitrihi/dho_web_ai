// DHO 아카이브 Text-to-SQL 챗봇 메인 페이지
"use client";

import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { useState } from "react";
import { JsonValue, MarkdownText } from "./components/rich-content";

const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

export default function Home() {
  const { messages, sendMessage, status, error } = useChat({
    transport: new DefaultChatTransport({ api: `${basePath}/api/chat` }),
  });
  const [input, setInput] = useState("");

  const busy = status === "submitted" || status === "streaming";

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    sendMessage({ text });
    setInput("");
  }

  return (
    <div className="d-flex flex-column flex-grow-1 bg-body text-body">
      <header className="d-flex align-items-center justify-content-between border-bottom bg-body px-3 py-2">
        <div>
          <h1 className="fs-6 fw-bold mb-0">대항해시대 온라인 DB 아카이브 — AI 검색</h1>
          <p className="small text-body-secondary mb-0">dho_structured.sqlite3 기반 Text-to-SQL 챗봇</p>
        </div>
        <a href={`${basePath}/logs`} className="small link-secondary">
          에러 로그
        </a>
      </header>

      <main className="mx-auto w-100 flex-grow-1 overflow-auto p-3 d-flex flex-column gap-3" style={{ maxWidth: "48rem" }}>
        {messages.length === 0 && (
          <p className="small text-body-secondary">
            예: &quot;준사관 우대 스킬 알려줘&quot;, &quot;코모두스 황제의 검 어디서 구해?&quot;
          </p>
        )}
        {messages.map((m, idx) => {
          const hasText = m.parts.some((part) => part.type === "text");
          const stalled =
            m.role === "assistant" && !hasText && !busy && idx === messages.length - 1;
          return (
          <div key={m.id} className={"d-flex " + (m.role === "user" ? "justify-content-end" : "justify-content-start")}>
            <div style={{ maxWidth: "85%" }}>
              <div
                className={
                  "rounded-3 px-3 py-2 small " +
                  (m.role === "user" ? "bg-primary text-white" : "bg-body-secondary border")
                }
              >
                {m.parts.map((part, i) => {
                  if (part.type === "text") {
                    return <MarkdownText key={i} text={part.text} />;
                  }
                  if (part.type === "dynamic-tool" || part.type.startsWith("tool-")) {
                    const p = part as {
                      type: string;
                      toolName?: string;
                      state: string;
                      input?: unknown;
                      output?: unknown;
                      errorText?: string;
                    };
                    const name = p.toolName ?? p.type.replace(/^tool-/, "");
                    const finished = p.state === "output-available" || p.state === "output-error";
                    return (
                      <details key={i} className="my-1 rounded border bg-body-tertiary">
                        <summary className="chat-tool-summary px-2 py-1 font-monospace text-body-secondary" style={{ fontSize: "0.7rem" }}>
                          🔧 {name}
                          {p.input ? ` ${JSON.stringify(p.input)}` : ""} — {p.state}
                        </summary>
                        {finished && (
                          <div className="border-top px-2 py-2" style={{ fontSize: "0.7rem" }}>
                            {p.state === "output-available" && <JsonValue value={p.output} />}
                            {p.state === "output-error" && (
                              <span className="text-danger">{p.errorText}</span>
                            )}
                          </div>
                        )}
                      </details>
                    );
                  }
                  return null;
                })}
              </div>
              {stalled && (
                <p className="mt-1 small text-warning">
                  ⚠️ 도구 호출 한도에 도달해 답변을 끝맺지 못했습니다. 질문을 좀 더 구체적으로
                  나눠서 다시 물어봐 주세요.
                </p>
              )}
            </div>
          </div>
          );
        })}
        {error && (
          <p className="small text-danger">오류가 발생했습니다: {error.message}</p>
        )}
      </main>

      <form onSubmit={handleSubmit} className="border-top p-3">
        <div className="mx-auto d-flex gap-2" style={{ maxWidth: "48rem" }}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="질문을 입력하세요"
            className="form-control"
            disabled={busy}
          />
          <button type="submit" disabled={busy || !input.trim()} className="btn btn-primary">
            전송
          </button>
        </div>
      </form>
    </div>
  );
}
