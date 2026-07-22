import Link from "next/link";
import type { Post } from "@/lib/types";

const CATEGORY_COLOR: Record<Post["category"], string> = {
  tech: "text-wire-amber border-wire-amber/40",
  startup: "text-signal-teal border-signal-teal/40",
  cyber: "text-alert-red border-alert-red/40",
};

function formatDispatchTime(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function PostCard({ post }: { post: Post }) {
  return (
    <Link
      href={`/post/${post.id}`}
      className="group grid grid-cols-[auto_1fr] gap-4 py-5 border-b border-white/10"
    >
      <div className="font-mono text-[11px] text-muted pt-1 w-20 shrink-0">
        {formatDispatchTime(post.published_at)}
      </div>
      <div>
        <div className="flex items-center gap-2 mb-1.5">
          <span
            className={`font-mono text-[10px] uppercase tracking-widest border rounded-sm px-1.5 py-0.5 ${CATEGORY_COLOR[post.category]}`}
          >
            {post.category}
          </span>
          <span className="font-mono text-[11px] text-muted">{post.source}</span>
        </div>
        <h2 className="font-display text-lg leading-snug text-paper group-hover:text-wire-amber transition-colors">
          {post.title}
        </h2>
        {post.summary && (
          <p className="mt-1 text-sm text-muted leading-relaxed line-clamp-2">
            {post.summary}
          </p>
        )}
      </div>
    </Link>
  );
}
