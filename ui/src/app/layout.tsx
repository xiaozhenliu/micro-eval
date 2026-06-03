import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "micro-eval",
  description: "Agent evaluation workbench",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className="h-full antialiased dark"
    >
      <body className="min-h-full flex flex-col bg-neutral-950 text-neutral-100">
        <header className="border-b border-neutral-800 px-6 py-4">
          <div className="max-w-6xl mx-auto">
            <h1 className="text-lg font-semibold tracking-tight">
              micro-eval
            </h1>
          </div>
        </header>
        <main className="flex-1 px-6 py-8">
          <div className="max-w-6xl mx-auto">{children}</div>
        </main>
      </body>
    </html>
  );
}
