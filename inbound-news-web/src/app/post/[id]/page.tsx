import { notFound } from "next/navigation";
import Link from "next/link";
import { getPostById } from "@/lib/posts";

export default async function PostPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const post = await getPostById(id);

  if (!post) notFound();

  const date = new Date(post.published_at).toLocaleString("en-US", {
    dateStyle: "long",
    timeStyle: "short",
  });

  return (
    <article className="container">
      <div className="article-header">
        <Link href="/" className="see-all">
          ← Back to the wire
        </Link>
        <div className="tag" style={{ marginTop: 24 }}>
          {post.category}
        </div>
        <h1>{post.title}</h1>
        <div className="hero-meta" style={{ marginBottom: 0 }}>
          <span>{post.source}</span>
          <span>{date}</span>
        </div>
      </div>

      <div className="article-body">
        <p>{post.content}</p>
        {post.url && (
          <Link href={post.url} target="_blank" rel="noopener noreferrer" className="btn">
            Read original source
          </Link>
        )}
      </div>
    </article>
  );
}
