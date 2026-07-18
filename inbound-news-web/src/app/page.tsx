import { getAllPosts } from '@/lib/posts'

export default async function Home() {
  const posts = await getAllPosts()

  return (
    <main style={{ padding: '2rem' }}>
      <h1>Inbound News</h1>
      {posts.length === 0 && <p>No posts found.</p>}
      <ul>
        {posts.map((post) => (
          <li key={post.id} style={{ marginBottom: '1rem' }}>
            <strong>[{post.category}]</strong> {post.title}
            <br />
            <small>{post.source} — {new Date(post.published_at).toLocaleString()}</small>
          </li>
        ))}
      </ul>
    </main>
  )
}