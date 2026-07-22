import { notFound } from "next/navigation";
import { getPostsByCategory } from "@/lib/posts";
import { ArticleCard } from "@/components/ArticleCard";
import { CATEGORIES } from "@/lib/categories";
import type { Post } from "@/lib/types";

export default async function CategoryPage({
  params,
}: {
  params: Promise<{ category: string }>;
}) {
  const { category } = await params;
  const match = CATEGORIES.find((c) => c.slug === category);

  if (!match) {
    notFound();
  }

  const posts = await getPostsByCategory(category as Post["category"]);

  return (
    <section className="rail container" style={{ paddingTop: 48 }}>
      <div className="section-header">
        <div className="section-title">
          <span className="tick">└─</span> {match.label}
        </div>
        <span className="see-all" style={{ cursor: "default" }}>
          {posts.length} {posts.length === 1 ? "dispatch" : "dispatches"}
        </span>
      </div>

      {posts.length === 0 ? (
        <div className="empty-state">Nothing on this desk yet.</div>
      ) : (
        <div className="grid-3">
          {posts.map((post) => (
            <ArticleCard post={post} key={post.id} />
          ))}
        </div>
      )}
    </section>
  );
}
