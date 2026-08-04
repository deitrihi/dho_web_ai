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
    <div className="flex min-h-dvh flex-col bg-neutral-950 text-neutral-100">
      <header className="flex items-center justify-between border-b border-neutral-800 px-4 py-3">
        <div>
          <h1 className="text-sm font-bold">대항해시대 온라인 DB 아카이브 — AI 검색</h1>
          <p className="text-xs text-neutral-500">dho_structured.sqlite3 기반 Text-to-SQL 챗봇</p>
        </div>
        <a href={`${basePath}/logs`} className="text-xs text-neutral-500 underline hover:text-neutral-300">
          에러 로그
        </a>
      </header>

      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-4 overflow-y-auto p-4">
        {messages.length === 0 && (
          <p className="text-sm text-neutral-500">
            예: &quot;준사관 우대 스킬 알려줘&quot;, &quot;코모두스 황제의 검 어디서 구해?&quot;
          </p>
        )}
        {messages.map((m, idx) => {
          const hasText = m.parts.some((part) => part.type === "text");
          const stalled =
            m.role === "assistant" && !hasText && !busy && idx === messages.length - 1;
          return (
          <div key={m.id} className={m.role === "user" ? "self-end" : "self-start"}>
            <div
              className={
                "max-w-[85%] break-words rounded-lg px-3 py-2 text-sm " +
                (m.role === "user"
                  ? "ml-auto bg-blue-600 text-white"
                  : "bg-neutral-900 border border-neutral-800")
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
                    <details
                      key={i}
                      className="my-1 rounded border border-neutral-700 bg-neutral-800 text-[11px] text-neutral-300"
                    >
                      <summary className="cursor-pointer select-none break-all px-2 py-1 font-mono text-neutral-400">
                        🔧 {name}
                        {p.input ? ` ${JSON.stringify(p.input)}` : ""} — {p.state}
                      </summary>
                      {finished && (
                        <div className="border-t border-neutral-700 px-2 py-1.5">
                          {p.state === "output-available" && <JsonValue value={p.output} />}
                          {p.state === "output-error" && (
                            <span className="text-red-400">{p.errorText}</span>
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
              <p className="mt-1 text-xs text-amber-500">
                ⚠️ 도구 호출 한도에 도달해 답변을 끝맺지 못했습니다. 질문을 좀 더 구체적으로
                나눠서 다시 물어봐 주세요.
              </p>
            )}
          </div>
          );
        })}
        {error && (
          <p className="text-sm text-red-400">오류가 발생했습니다: {error.message}</p>
        )}
      </main>

      <form onSubmit={handleSubmit} className="border-t border-neutral-800 p-4">
        <div className="mx-auto flex max-w-3xl gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="질문을 입력하세요"
            className="flex-1 rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm outline-none focus:border-blue-500"
            disabled={busy}
          />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium disabled:opacity-40"
          >
            전송
          </button>
        </div>
      </form>
    </div>
  );
}
