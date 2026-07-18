export type Post = {
  id: string
  title: string
  category: 'tech' | 'startup' | 'cyber'
  source: string
  summary: string | null
  content: string
  url: string | null
  published_at: string
}
