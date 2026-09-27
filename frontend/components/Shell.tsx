"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/projects", label: "Projects" },
  { href: "/runs", label: "Runs" },
  { href: "/compare", label: "Compare" },
  { href: "/github", label: "GitHub" },
];

function active(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

function Mark() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <path d="M3.25 15.25V5.1A1.85 1.85 0 0 1 5.1 3.25h7.8a1.85 1.85 0 0 1 1.85 1.85v10.15" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      <path d="M7 15.25V9.1h4v6.15" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="min-h-screen md:grid md:grid-cols-[216px_1fr]">
      <aside className="border-b border-[var(--line)] px-3 py-5 md:sticky md:top-0 md:h-screen md:border-b-0 md:border-r">
        <Link href="/" className="flex items-center gap-2.5 rounded-lg px-2 py-1 hover:bg-[var(--hover)]">
          <Mark />
          <span className="text-sm font-semibold tracking-tight">AgentGate</span>
        </Link>
        <nav className="mt-6 flex gap-1 overflow-x-auto md:flex-col">
          {NAV.map((item) => {
            const on = active(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={on ? "page" : undefined}
                className={`rounded-lg px-2.5 py-1.5 text-sm ${
                  on ? "bg-[var(--surface)] font-medium shadow-[var(--shadow)]" : "text-[var(--muted)] hover:bg-[var(--hover)] hover:text-[var(--ink)]"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>
      <main className="mx-auto w-full max-w-[1040px] px-6 py-8 md:px-10">
        <div key={pathname} className="enter">
          {children}
        </div>
      </main>
    </div>
  );
}
