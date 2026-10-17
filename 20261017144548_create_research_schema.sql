/*
# Research Agent Schema

1. Overview
- This migration creates the core data model for the AI Web Research Agent.
- Single-tenant application (no sign-in), so policies allow anon + authenticated CRUD.

2. New Tables
- `research_jobs` — top-level research job configuration, status, counters, timestamps.
- `search_queries` — individual search queries generated for a job, with execution status.
- `source_pages` — URLs discovered/fetched for a job, with fetch metadata and status.
- `research_records` — extracted structured records (JSONB fields) with validation status.
- `export_jobs` — export metadata (format, destination, status, file info).

3. Security
- RLS enabled on all tables.
- Policies allow anon + authenticated full CRUD (single-tenant, intentionally shared data).

4. Indexes
- research_jobs: status, created_at
- search_queries: job_id, status
- source_pages: job_id, url (unique per job), fetch_status
- research_records: job_id, validation_status, dedup_key
- export_jobs: job_id, status
*/

CREATE TABLE IF NOT EXISTS research_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text,
  prompt text NOT NULL,
  objective text,
  search_queries jsonb NOT NULL DEFAULT '[]'::jsonb,
  target_count integer NOT NULL DEFAULT 100,
  batch_size integer NOT NULL DEFAULT 20,
  max_concurrency integer NOT NULL DEFAULT 3,
  fields jsonb NOT NULL DEFAULT '[]'::jsonb,
  inclusion_rules jsonb DEFAULT '[]'::jsonb,
  exclusion_rules jsonb DEFAULT '[]'::jsonb,
  dedup_keys jsonb NOT NULL DEFAULT '["name"]'::jsonb,
  geography text,
  export_format text DEFAULT 'xlsx',
  status text NOT NULL DEFAULT 'draft',
  queries_executed integer NOT NULL DEFAULT 0,
  urls_discovered integer NOT NULL DEFAULT 0,
  pages_fetched integer NOT NULL DEFAULT 0,
  records_extracted integer NOT NULL DEFAULT 0,
  records_validated integer NOT NULL DEFAULT 0,
  duplicates_removed integer NOT NULL DEFAULT 0,
  failed_records integer NOT NULL DEFAULT 0,
  error_message text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE research_jobs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "anon_select_research_jobs" ON research_jobs;
CREATE POLICY "anon_select_research_jobs" ON research_jobs FOR SELECT TO anon, authenticated USING (true);
DROP POLICY IF EXISTS "anon_insert_research_jobs" ON research_jobs;
CREATE POLICY "anon_insert_research_jobs" ON research_jobs FOR INSERT TO anon, authenticated WITH CHECK (true);
DROP POLICY IF EXISTS "anon_update_research_jobs" ON research_jobs;
CREATE POLICY "anon_update_research_jobs" ON research_jobs FOR UPDATE TO anon, authenticated USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "anon_delete_research_jobs" ON research_jobs;
CREATE POLICY "anon_delete_research_jobs" ON research_jobs FOR DELETE TO anon, authenticated USING (true);

CREATE INDEX IF NOT EXISTS idx_research_jobs_status ON research_jobs(status);
CREATE INDEX IF NOT EXISTS idx_research_jobs_created ON research_jobs(created_at);

CREATE TABLE IF NOT EXISTS search_queries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id uuid NOT NULL REFERENCES research_jobs(id) ON DELETE CASCADE,
  query text NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  result_count integer DEFAULT 0,
  error text,
  executed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE search_queries ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "anon_select_search_queries" ON search_queries;
CREATE POLICY "anon_select_search_queries" ON search_queries FOR SELECT TO anon, authenticated USING (true);
DROP POLICY IF EXISTS "anon_insert_search_queries" ON search_queries;
CREATE POLICY "anon_insert_search_queries" ON search_queries FOR INSERT TO anon, authenticated WITH CHECK (true);
DROP POLICY IF EXISTS "anon_update_search_queries" ON search_queries;
CREATE POLICY "anon_update_search_queries" ON search_queries FOR UPDATE TO anon, authenticated USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "anon_delete_search_queries" ON search_queries;
CREATE POLICY "anon_delete_search_queries" ON search_queries FOR DELETE TO anon, authenticated USING (true);

CREATE INDEX IF NOT EXISTS idx_search_queries_job ON search_queries(job_id);
CREATE INDEX IF NOT EXISTS idx_search_queries_status ON search_queries(status);

CREATE TABLE IF NOT EXISTS source_pages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id uuid NOT NULL REFERENCES research_jobs(id) ON DELETE CASCADE,
  url text NOT NULL,
  title text,
  fetch_status text NOT NULL DEFAULT 'pending',
  http_status integer,
  content_length integer,
  retrieved_at timestamptz,
  error text,
  raw_content text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(job_id, url)
);
ALTER TABLE source_pages ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "anon_select_source_pages" ON source_pages;
CREATE POLICY "anon_select_source_pages" ON source_pages FOR SELECT TO anon, authenticated USING (true);
DROP POLICY IF EXISTS "anon_insert_source_pages" ON source_pages;
CREATE POLICY "anon_insert_source_pages" ON source_pages FOR INSERT TO anon, authenticated WITH CHECK (true);
DROP POLICY IF EXISTS "anon_update_source_pages" ON source_pages;
CREATE POLICY "anon_update_source_pages" ON source_pages FOR UPDATE TO anon, authenticated USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "anon_delete_source_pages" ON source_pages;
CREATE POLICY "anon_delete_source_pages" ON source_pages FOR DELETE TO anon, authenticated USING (true);

CREATE INDEX IF NOT EXISTS idx_source_pages_job ON source_pages(job_id);
CREATE INDEX IF NOT EXISTS idx_source_pages_fetch_status ON source_pages(fetch_status);

CREATE TABLE IF NOT EXISTS research_records (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id uuid NOT NULL REFERENCES research_jobs(id) ON DELETE CASCADE,
  source_page_id uuid REFERENCES source_pages(id) ON DELETE SET NULL,
  fields jsonb NOT NULL DEFAULT '{}'::jsonb,
  validation_status text NOT NULL DEFAULT 'pending',
  dedup_key text,
  is_duplicate boolean NOT NULL DEFAULT false,
  error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE research_records ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "anon_select_research_records" ON research_records;
CREATE POLICY "anon_select_research_records" ON research_records FOR SELECT TO anon, authenticated USING (true);
DROP POLICY IF EXISTS "anon_insert_research_records" ON research_records;
CREATE POLICY "anon_insert_research_records" ON research_records FOR INSERT TO anon, authenticated WITH CHECK (true);
DROP POLICY IF EXISTS "anon_update_research_records" ON research_records;
CREATE POLICY "anon_update_research_records" ON research_records FOR UPDATE TO anon, authenticated USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "anon_delete_research_records" ON research_records;
CREATE POLICY "anon_delete_research_records" ON research_records FOR DELETE TO anon, authenticated USING (true);

CREATE INDEX IF NOT EXISTS idx_research_records_job ON research_records(job_id);
CREATE INDEX IF NOT EXISTS idx_research_records_validation ON research_records(validation_status);
CREATE INDEX IF NOT EXISTS idx_research_records_dedup ON research_records(job_id, dedup_key);

CREATE TABLE IF NOT EXISTS export_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id uuid NOT NULL REFERENCES research_jobs(id) ON DELETE CASCADE,
  format text NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  file_path text,
  file_size integer,
  record_count integer,
  columns jsonb DEFAULT '[]'::jsonb,
  destination text,
  error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
);
ALTER TABLE export_jobs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "anon_select_export_jobs" ON export_jobs;
CREATE POLICY "anon_select_export_jobs" ON export_jobs FOR SELECT TO anon, authenticated USING (true);
DROP POLICY IF EXISTS "anon_insert_export_jobs" ON export_jobs;
CREATE POLICY "anon_insert_export_jobs" ON export_jobs FOR INSERT TO anon, authenticated WITH CHECK (true);
DROP POLICY IF EXISTS "anon_update_export_jobs" ON export_jobs;
CREATE POLICY "anon_update_export_jobs" ON export_jobs FOR UPDATE TO anon, authenticated USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "anon_delete_export_jobs" ON export_jobs;
CREATE POLICY "anon_delete_export_jobs" ON export_jobs FOR DELETE TO anon, authenticated USING (true);

CREATE INDEX IF NOT EXISTS idx_export_jobs_job ON export_jobs(job_id);
CREATE INDEX IF NOT EXISTS idx_export_jobs_status ON export_jobs(status);
