import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DHO 아카이브 AI 챗봇",
  description: "대항해시대 온라인 DB 아카이브 AI 검색",
};

// webapp(base.html)과 동일한 OS 다크모드 감지 로직 — 렌더링 전에 즉시 data-bs-theme를
// 설정해 깜빡임을 막고, iframe으로 임베드된 상태에서도 부모 페이지와 테마가 어긋나지 않게 함.
const themeScript = `
(function () {
  var mq = window.matchMedia('(prefers-color-scheme: dark)');
  function apply() { document.documentElement.setAttribute('data-bs-theme', mq.matches ? 'dark' : 'light'); }
  apply();
  mq.addEventListener('change', apply);
})();
`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko" className="h-100" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
        <link
          href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css"
          rel="stylesheet"
        />
      </head>
      <body className="d-flex flex-column min-vh-100">{children}</body>
    </html>
  );
}
