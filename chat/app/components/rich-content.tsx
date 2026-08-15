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
        p: (props) => <p className="mb-2" {...props} />,
        ul: (props) => <ul className="mb-2 ps-4" {...props} />,
        ol: (props) => <ol className="mb-2 ps-4" {...props} />,
        li: (props) => <li className="mb-1" {...props} />,
        strong: (props) => <strong className="fw-semibold" {...props} />,
        a: (props) => <a target="_blank" rel="noreferrer" {...props} />,
        h1: (props) => <h1 className="mb-2 fs-6 fw-bold" {...props} />,
        h2: (props) => <h2 className="mb-2 fs-6 fw-bold" {...props} />,
        h3: (props) => <h3 className="mb-1 fs-6 fw-semibold" {...props} />,
        blockquote: (props) => (
          <blockquote className="mb-2 border-start ps-2 text-body-secondary" {...props} />
        ),
        hr: () => <hr className="my-2" />,
        pre: (props) => (
          <pre
            className="mb-2 overflow-x-auto rounded border bg-body-tertiary p-2 font-monospace"
            style={{ fontSize: "0.85em" }}
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
            <code
              className="rounded bg-body-tertiary px-1 font-monospace"
              style={{ fontSize: "0.85em" }}
              {...props}
            >
              {children}
            </code>
          );
        },
        table: (props) => (
          <div className="mb-2 overflow-x-auto">
            <table className="table table-sm table-bordered mb-0" {...props} />
          </div>
        ),
        th: (props) => <th {...props} />,
        td: (props) => <td className="align-top" {...props} />,
      }}
    >
      {text}
    </ReactMarkdown>
  );
}

// tool 실행 결과(JSON)를 배열-of-객체는 표로, 객체는 key-value 목록으로, 그 외엔 텍스트로 표시
export function JsonValue({ value }: { value: unknown }) {
  if (value === null || value === undefined) {
    return <span className="text-body-secondary">—</span>;
  }

  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-body-secondary">(없음)</span>;
    const allPlainObjects = value.every(
      (v) => v !== null && typeof v === "object" && !Array.isArray(v)
    );
    if (allPlainObjects) {
      return <JsonTable rows={value as Record<string, unknown>[]} />;
    }
    return (
      <ul className="ps-3 mb-0">
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
    if (entries.length === 0) return <span className="text-body-secondary">{"{}"}</span>;
    return (
      <div className="d-flex flex-column gap-1">
        {entries.map(([k, v]) => (
          <div key={k}>
            <div className="text-uppercase text-body-secondary" style={{ fontSize: "0.9em" }}>{k}</div>
            <div className="ps-1">
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
      <table className="table table-sm table-bordered mb-0">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <td key={c} className="align-top">
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
