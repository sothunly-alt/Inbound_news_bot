import Link from "next/link";
import type { Post } from "@/lib/types";

const CATEGORY_TAG: Record<Post["category"], string> = {
  tech: "Tech",
  startup: "Startup",
  cyber: "Cybersecurity",
};

function formatMeta(post: Post) {
  const date = new Date(post.published_at).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
  return `${post.source} · ${date}`;
}

export function ArticleCard({ post }: { post: Post }) {
  return (
    <article className="card">
      <div>
        <div className="tag">{CATEGORY_TAG[post.category]}</div>
        <h3>
          <Link href={`/post/${post.id}`} style={{ textDecoration: "none" }}>
            {post.title}
          </Link>
        </h3>
        {post.summary && <p>{post.summary}</p>}
      </div>
      <div className="card-footer">
        <span>{formatMeta(post)}</span>
        <span className="card-arrow">↗</span>
      </div>
    </article>
  );
}
