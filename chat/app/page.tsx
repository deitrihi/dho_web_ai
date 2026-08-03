// DHO 아카이브 Text-to-SQL 챗봇 메인 페이지
"use client";

import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { useState } from "react";

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
    <div className="flex min-h-screen flex-col bg-neutral-950 text-neutral-100">
      <header className="border-b border-neutral-800 px-4 py-3">
        <h1 className="text-sm font-bold">대항해시대 온라인 DB 아카이브 — AI 검색</h1>
        <p className="text-xs text-neutral-500">dho_structured.sqlite3 기반 Text-to-SQL 챗봇</p>
      </header>

      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-4 overflow-y-auto p-4">
        {messages.length === 0 && (
          <p className="text-sm text-neutral-500">
            예: &quot;준사관 우대 스킬 알려줘&quot;, &quot;코모두스 황제의 검 어디서 구해?&quot;
          </p>
        )}
        {messages.map((m) => (
          <div key={m.id} className={m.role === "user" ? "self-end" : "self-start"}>
            <div
              className={
                "max-w-[85%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap " +
                (m.role === "user"
                  ? "ml-auto bg-blue-600 text-white"
                  : "bg-neutral-900 border border-neutral-800")
              }
            >
              {m.parts.map((part, i) => {
                if (part.type === "text") {
                  return <span key={i}>{part.text}</span>;
                }
                if (part.type === "dynamic-tool" || part.type.startsWith("tool-")) {
                  const p = part as {
                    type: string;
                    toolName?: string;
                    state: string;
                    input?: unknown;
                  };
                  const name = p.toolName ?? p.type.replace(/^tool-/, "");
                  return (
                    <div
                      key={i}
                      className="my-1 rounded border border-neutral-700 bg-neutral-800 px-2 py-1 font-mono text-[11px] text-neutral-400"
                    >
                      🔧 {name}
                      {p.input ? ` ${JSON.stringify(p.input)}` : ""} — {p.state}
                    </div>
                  );
                }
                return null;
              })}
            </div>
          </div>
        ))}
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
