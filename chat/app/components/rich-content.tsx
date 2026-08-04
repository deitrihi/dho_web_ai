// 챗봇 응답을 내용에 맞춰(마크다운 표/목록/코드, 도구 결과 JSON) 다르게 렌더링하는 컴포넌트 모음
"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import type { ComponentPropsWithoutRef } from "react";

export function MarkdownText({ text }: { text: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkBreaks]}
      components={{
        p: (props) => <p className="mb-2 last:mb-0" {...props} />,
        ul: (props) => <ul className="mb-2 list-disc pl-5 last:mb-0" {...props} />,
        ol: (props) => <ol className="mb-2 list-decimal pl-5 last:mb-0" {...props} />,
        li: (props) => <li className="mb-0.5" {...props} />,
        strong: (props) => <strong className="font-semibold text-neutral-100" {...props} />,
        a: (props) => (
          <a className="text-blue-400 underline" target="_blank" rel="noreferrer" {...props} />
        ),
        h1: (props) => <h1 className="mb-2 text-base font-bold" {...props} />,
        h2: (props) => <h2 className="mb-2 text-sm font-bold" {...props} />,
        h3: (props) => <h3 className="mb-1 text-sm font-semibold" {...props} />,
        blockquote: (props) => (
          <blockquote
            className="mb-2 border-l-2 border-neutral-700 pl-2 text-neutral-400 last:mb-0"
            {...props}
          />
        ),
        hr: () => <hr className="my-2 border-neutral-800" />,
        pre: (props) => (
          <pre
            className="mb-2 overflow-x-auto rounded-md border border-neutral-800 bg-neutral-950 p-2 font-mono text-[0.85em] last:mb-0"
            {...props}
          />
        ),
        code: ({ className, children, ...props }: ComponentPropsWithoutRef<"code">) => {
          const isBlock = Boolean(className); // remark-gfm이 fenced code에만 language-* 클래스를 붙임
          if (isBlock) {
            return (
              <code className={className} {...props}>
                {children}
              </code>
            );
          }
          return (
            <code className="rounded bg-neutral-800 px-1 py-0.5 font-mono text-[0.85em]" {...props}>
              {children}
            </code>
          );
        },
        table: (props) => (
          <div className="mb-2 overflow-x-auto last:mb-0">
            <table className="w-full border-collapse text-xs" {...props} />
          </div>
        ),
        thead: (props) => <thead className="bg-neutral-800" {...props} />,
        th: (props) => (
          <th className="border border-neutral-700 px-2 py-1 text-left font-medium" {...props} />
        ),
        td: (props) => <td className="border border-neutral-800 px-2 py-1 align-top" {...props} />,
      }}
    >
      {text}
    </ReactMarkdown>
  );
}

// tool 실행 결과(JSON)를 배열-of-객체는 표로, 객체는 key-value 목록으로, 그 외엔 텍스트로 표시
export function JsonValue({ value }: { value: unknown }) {
  if (value === null || value === undefined) {
    return <span className="text-neutral-600">—</span>;
  }

  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-neutral-600">(없음)</span>;
    const allPlainObjects = value.every(
      (v) => v !== null && typeof v === "object" && !Array.isArray(v)
    );
    if (allPlainObjects) {
      return <JsonTable rows={value as Record<string, unknown>[]} />;
    }
    return (
      <ul className="list-disc pl-4">
        {value.map((v, i) => (
          <li key={i}>
            <JsonValue value={v} />
          </li>
        ))}
      </ul>
    );
  }

  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return <span className="text-neutral-600">{"{}"}</span>;
    return (
      <div className="space-y-1.5">
        {entries.map(([k, v]) => (
          <div key={k}>
            <div className="text-[10px] uppercase tracking-wide text-neutral-500">{k}</div>
            <div className="pl-1">
              <JsonValue value={v} />
            </div>
          </div>
        ))}
      </div>
    );
  }

  return <span>{String(value)}</span>;
}

function JsonTable({ rows }: { rows: Record<string, unknown>[] }) {
  const columns = Array.from(new Set(rows.flatMap((r) => Object.keys(r))));
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-xs">
        <thead className="bg-neutral-800">
          <tr>
            {columns.map((c) => (
              <th key={c} className="border border-neutral-700 px-2 py-1 text-left font-medium">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <td key={c} className="border border-neutral-800 px-2 py-1 align-top">
                  <JsonValue value={row[c]} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
