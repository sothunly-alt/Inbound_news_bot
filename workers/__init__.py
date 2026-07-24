"""Inbound News Bot — Ingestion Workers.

Run from the repo root:
    python -m workers.ingest_apis     # pull from GDELT + NewsData.io
    python -m workers.rss_bulk        # pull from feeds_bulk.txt
    python -m workers.dedup           # cluster articles into stories

Environment variables required:
    SUPABASE_URL           — your Supabase project URL
    SUPABASE_SERVICE_ROLE_KEY — service-role key (NOT anon key)
    NEWSDATA_API_KEY       — from newsdata.io (optional, free tier)
    COHERE_API_KEY         — from cohere.com (for dedup embeddings)
"""
