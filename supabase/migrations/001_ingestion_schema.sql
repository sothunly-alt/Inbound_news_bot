-- Inbound News Bot — Ingestion Schema
-- Run this in your Supabase SQL Editor to create the tables.
-- Requires: pgvector extension (enable in Supabase Dashboard → Extensions).

-- 1. Enable pgvector for embeddings
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Raw ingested articles (from APIs + RSS)
CREATE TABLE IF NOT EXISTS articles (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  title TEXT NOT NULL,
  summary TEXT,
  url TEXT UNIQUE NOT NULL,
  source_name TEXT,
  source_domain TEXT,
  category TEXT,
  language TEXT DEFAULT 'en',
  published_at TIMESTAMPTZ,
  ingested_at TIMESTAMPTZ DEFAULT NOW(),
  raw_json JSONB
);

-- 3. Deduplicated stories (clustered articles)
CREATE TABLE IF NOT EXISTS stories (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  title TEXT NOT NULL,
  summary_en TEXT,
  source_count INT DEFAULT 1,
  category TEXT,
  tags TEXT[],
  embedding VECTOR(1024),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Source reference links (many-to-many: stories ↔ articles)
CREATE TABLE IF NOT EXISTS story_sources (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  story_id UUID REFERENCES stories(id) ON DELETE CASCADE,
  article_id UUID REFERENCES articles(id) ON DELETE CASCADE,
  source_name TEXT,
  source_url TEXT
);

-- 5. Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_articles_domain ON articles(source_domain);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category);
CREATE INDEX IF NOT EXISTS idx_articles_language ON articles(language);
CREATE INDEX IF NOT EXISTS idx_stories_category ON stories(category);
CREATE INDEX IF NOT EXISTS idx_stories_created ON stories(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_story_sources_story ON story_sources(story_id);
CREATE INDEX IF NOT EXISTS idx_story_sources_article ON story_sources(article_id);

-- 6. Vector index for similarity search (run after inserting initial data)
-- CREATE INDEX IF NOT EXISTS stories_embedding_idx
--   ON stories USING ivfflat (embedding vector_cosine_ops)
--   WITH (lists = 100);

-- 7. Row Level Security (RLA) — public read, service-role write
ALTER TABLE articles ENABLE ROW LEVEL SECURITY;
ALTER TABLE stories ENABLE ROW LEVEL SECURITY;
ALTER TABLE story_sources ENABLE ROW LEVEL SECURITY;

-- Public can read articles and stories
CREATE POLICY "Public can read articles" ON articles FOR SELECT USING (true);
CREATE POLICY "Public can read stories" ON stories FOR SELECT USING (true);
CREATE POLICY "Public can read story_sources" ON story_sources FOR SELECT USING (true);

-- Only service role can insert/update/delete (the ingestion worker)
CREATE POLICY "Service role can manage articles" ON articles FOR ALL
  USING (auth.role() = 'service_role');
CREATE POLICY "Service role can manage stories" ON stories FOR ALL
  USING (auth.role() = 'service_role');
CREATE POLICY "Service role can manage story_sources" ON story_sources FOR ALL
  USING (auth.role() = 'service_role');
