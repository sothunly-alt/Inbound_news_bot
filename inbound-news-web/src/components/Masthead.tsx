import Link from "next/link";
import { getAllPosts } from "@/lib/posts";

const CHANNELS = [
  { slug: "tech", label: "TECH" },
  { slug: "startup", label: "STARTUP" },
  { slug: "cyber", label: "CYBER" },
];

export async function Masthead() {
  const posts = await getAllPosts();
  const ticker = posts.slice(0, 8);

  return (
    <header className="border-b border-white/10">
      <div className="mx-auto max-w-3xl px-4 pt-6 pb-4 flex items-baseline justify-between">
        <Link href="/" className="font-display text-2xl tracking-tight text-paper">
          INBOUND<span className="text-wire-amber">/</span>
        </Link>
        <nav className="font-mono text-xs uppercase tracking-widest text-muted flex gap-4">
          {CHANNELS.map((c) => (
            <Link
              key={c.slug}
              href={`/${c.slug}`}
              className="hover:text-paper transition-colors"
            >
              {c.label}
            </Link>
          ))}
        </nav>
      </div>

      {ticker.length > 0 && (
        <div className="overflow-hidden border-t border-white/10 bg-white/[0.03]">
          <div
            className="mx-auto max-w-3xl px-4 py-2 font-mono text-[11px] text-muted whitespace-nowrap overflow-x-auto"
            style={{ scrollbarWidth: "none" }}
          >
            {ticker.map((p, i) => (
              <span key={p.id}>
                <span className="text-wire-amber">●</span> {p.title}
                {i < ticker.length - 1 && (
                  <span className="mx-4 text-white/20">//</span>
                )}
              </span>
            ))}
          </div>
        </div>
      )}
    </header>
  );
}
