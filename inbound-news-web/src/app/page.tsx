import Link from "next/link";
import { getAllPosts, getPostsByCategory } from "@/lib/posts";
import { ArticleCard } from "@/components/ArticleCard";
import { CATEGORIES } from "@/lib/categories";
import { DonateSection } from "@/components/DonateSection";
import type { Post } from "@/lib/types";

function formatMeta(post: Post) {
  const date = new Date(post.published_at).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
  return { source: post.source, date };
}

export default async function Home() {
  const posts = await getAllPosts();

  if (posts.length === 0) {
    return (
      <section className="container">
        <div className="empty-state">The wire is quiet — no dispatches yet.</div>
      </section>
    );
  }

  const [lead, ...rest] = posts;
  const sideStories = rest.slice(0, 3);
  const mostRead = posts.slice(0, 4);
  const leadMeta = formatMeta(lead);
  const uniqueSources = new Set(posts.map((p) => p.source)).size;

  const rails = await Promise.all(
    CATEGORIES.map(async (c) => ({
      ...c,
      posts: (await getPostsByCategory(c.slug)).slice(0, 3),
    }))
  );

  return (
    <>
      {/* Hero */}
      <section className="hero container">
        <article className="hero-main">
          <div className="tag">{lead.category}</div>
          <h1>
            <Link href={`/post/${lead.id}`} style={{ textDecoration: "none", color: "inherit" }}>
              {lead.title}
            </Link>
          </h1>
          {lead.summary && <p className="hero-dek">{lead.summary}</p>}
          <div className="hero-meta">
            <span>{leadMeta.source}</span>
            <span>{leadMeta.date}</span>
          </div>
          <div className="hero-img" />
        </article>
        <aside className="hero-side">
          {sideStories.map((post) => (
            <div className="side-card" key={post.id}>
              <div className="tag">{post.category}</div>
              <h3>
                <Link href={`/post/${post.id}`} style={{ textDecoration: "none" }}>
                  {post.title}
                </Link>
              </h3>
              <div className="hero-meta" style={{ marginBottom: 0 }}>
                <span>{post.source}</span>
              </div>
            </div>
          ))}
        </aside>
      </section>

      {/* Category rails */}
      {rails
        .filter((r) => r.posts.length > 0)
        .map((rail) => (
          <section className="rail container" key={rail.slug}>
            <div className="section-header">
              <div className="section-title">
                <span className="tick">└─</span> {rail.label}
              </div>
              <Link href={`/${rail.slug}`} className="see-all">
                See all {rail.label}
              </Link>
            </div>
            <div className="grid-3">
              {rail.posts.map((post) => (
                <ArticleCard post={post} key={post.id} />
              ))}
            </div>
          </section>
        ))}

      {/* Stats strip */}
      <section className="stats-strip container">
        <div className="stat-item">
          <div className="stat-num">{String(posts.length).padStart(2, "0")}</div>
          <div className="stat-label">Stories Filed</div>
        </div>
        <div className="stat-item">
          <div className="stat-num">{String(uniqueSources).padStart(2, "0")}</div>
          <div className="stat-label">Sources Tracked</div>
        </div>
        <div className="stat-item">
          <div className="stat-num">{String(CATEGORIES.length).padStart(2, "0")}</div>
          <div className="stat-label">Desks</div>
        </div>
        <div className="stat-item">
          <div className="stat-num">24/7</div>
          <div className="stat-label">Wire Coverage</div>
        </div>
      </section>

      {/* Most read */}
      <section className="split-layout container">
        <aside className="most-read">
          <div className="section-header">
            <div className="section-title">
              <span className="tick">└─</span> Latest In
            </div>
          </div>
          <ol>
            {mostRead.map((post) => (
              <li key={post.id}>
                <div>
                  <div className="tag">{post.category}</div>
                  <h4>
                    <Link href={`/post/${post.id}`} style={{ textDecoration: "none" }}>
                      {post.title}
                    </Link>
                  </h4>
                </div>
              </li>
            ))}
          </ol>
        </aside>
        <div>
          <div className="section-header">
            <div className="section-title">
              <span className="tick">└─</span> All Dispatches
            </div>
          </div>
          <div className="grid-3">
            {posts.slice(0, 6).map((post) => (
              <ArticleCard post={post} key={post.id} />
            ))}
          </div>
        </div>
      </section>

      {/* Donate */}
      <DonateSection />
    </>
  );
}
