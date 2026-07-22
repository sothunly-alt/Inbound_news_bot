import { getAllPosts } from "@/lib/posts";

export async function Ticker() {
  const posts = await getAllPosts();
  const items = posts.slice(0, 10);

  if (items.length === 0) return null;

  // Duplicated so the CSS scroll animation (-50%) loops seamlessly.
  const track = [...items, ...items];

  return (
    <div className="ticker">
      <div className="ticker-track">
        {track.map((post, i) => (
          <div
            key={`${post.id}-${i}`}
            className={`ticker-item${post.category === "cyber" ? " breaking" : ""}`}
          >
            {post.title}
          </div>
        ))}
      </div>
    </div>
  );
}
