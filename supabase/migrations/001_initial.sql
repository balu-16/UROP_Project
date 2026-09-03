-- RAGnostic initial schema: Supabase Postgres truth + Chroma vector index
-- Replaces Mongo collections. PG is truth; Chroma is rebuildable index.

-- Enable UUID generation
create extension if not exists "pgcrypto";

-- ── Users (JWT custom) ──────────────────────────────────────────────────
create table if not exists users (
  _id text primary key,
  email text not null unique,
  name text not null check (char_length(name) between 1 and 120),
  password_hash text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  token_invalid_before timestamptz
);
create index if not exists users_email_idx on users (lower(email));
create index if not exists users_created_idx on users (created_at desc);

-- ── Auth sessions (refresh tokens, renamed from 'sessions' to avoid keyword) ──
create table if not exists auth_sessions (
  _id text primary key,
  user_id text not null references users(_id) on delete cascade,
  refresh_hash text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  expires_at timestamptz not null,
  revoked boolean not null default false
);
create index if not exists auth_sessions_user_created_idx on auth_sessions (user_id, created_at desc);
create index if not exists auth_sessions_refresh_hash_idx on auth_sessions (refresh_hash);
create index if not exists auth_sessions_expires_idx on auth_sessions (expires_at);
-- Legacy alias: create view 'sessions' so old queries still work if needed
-- (AppDatabase maps collection("sessions") -> auth_sessions, no view needed)

-- ── Chat sessions ───────────────────────────────────────────────────────
create table if not exists chat_sessions (
  _id text primary key,
  user_id text not null references users(_id) on delete cascade,
  title text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists chat_sessions_user_updated_idx on chat_sessions (user_id, updated_at desc);

-- ── Messages ────────────────────────────────────────────────────────────
create table if not exists messages (
  _id text primary key,
  user_id text not null references users(_id) on delete cascade,
  session_id text not null references chat_sessions(_id) on delete cascade,
  role text not null check (role in ('user','assistant')),
  content text not null,
  selected_arm text check (selected_arm in ('standard_rag','graph_rag_1hop','graph_rag_2hop','hybrid')),
  sources jsonb not null default '[]'::jsonb,
  reward jsonb,
  latency_ms integer,
  reasoning_metadata jsonb,
  retrieval_diagnostics jsonb,
  retrieval_log_id text,
  created_at timestamptz not null default now()
);
create index if not exists messages_session_created_idx on messages (session_id, created_at);
create index if not exists messages_user_idx on messages (user_id);

-- ── Retrieval logs ──────────────────────────────────────────────────────
create table if not exists retrieval_logs (
  _id text primary key,
  user_id text not null references users(_id) on delete cascade,
  session_id text not null references chat_sessions(_id) on delete cascade,
  message_id text not null,
  selected_arm text not null,
  arm_scores jsonb not null default '{}'::jsonb,
  feature_vector jsonb,
  retrieved_chunks jsonb not null default '[]'::jsonb,
  diagnostics jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists retrieval_logs_session_created_idx on retrieval_logs (session_id, created_at desc);
create index if not exists retrieval_logs_user_idx on retrieval_logs (user_id);

-- ── Reward logs ─────────────────────────────────────────────────────────
create table if not exists reward_logs (
  _id text primary key,
  user_id text not null references users(_id) on delete cascade,
  session_id text not null references chat_sessions(_id) on delete cascade,
  message_id text not null,
  rating double precision check (rating between 0 and 1),
  comment text check (char_length(comment) <= 2000),
  reward double precision,
  quality double precision,
  faithfulness double precision,
  cost double precision,
  latency_ms integer,
  token_usage jsonb,
  created_at timestamptz not null default now()
);
create index if not exists reward_logs_session_created_idx on reward_logs (session_id, created_at desc);

-- ── Indexed documents (legacy, per-upload metadata) ────────────────────
create table if not exists indexed_documents (
  _id text primary key,
  user_id text not null references users(_id) on delete cascade,
  session_id text not null default '',
  filename text not null,
  metadata jsonb not null default '{}'::jsonb,
  chunk_count integer not null default 0,
  created_at timestamptz not null default now()
);
create index if not exists indexed_documents_user_created_idx on indexed_documents (user_id, created_at desc);
create index if not exists indexed_documents_session_idx on indexed_documents (session_id);

-- ── Documents (PG truth, Chroma rebuildable) ───────────────────────────
create table if not exists documents (
  id uuid primary key default gen_random_uuid(),
  user_id text references users(_id) on delete cascade,
  title text,
  source text,
  content text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists documents_user_created_idx on documents (user_id, created_at desc);

-- ── Chunks ──────────────────────────────────────────────────────────────
create table if not exists chunks (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references documents(id) on delete cascade,
  chunk_index integer not null,
  content text not null,
  chunk_id text unique, -- ULID chk_... used as Chroma id
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists chunks_document_idx on chunks (document_id);
create index if not exists chunks_chunk_id_idx on chunks (chunk_id);

-- ── Entities ────────────────────────────────────────────────────────────
create table if not exists entities (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  type text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists entities_name_idx on entities (lower(name));
create unique index if not exists entities_name_type_unique on entities (lower(name), coalesce(type,''));

-- ── Chunk ↔ Entities (M:N) ──────────────────────────────────────────────
create table if not exists chunk_entities (
  chunk_id uuid not null references chunks(id) on delete cascade,
  entity_id uuid not null references entities(id) on delete cascade,
  primary key (chunk_id, entity_id)
);
create index if not exists chunk_entities_entity_idx on chunk_entities (entity_id);

-- ── Relationships (graph edges) ─────────────────────────────────────────
create table if not exists relationships (
  id uuid primary key default gen_random_uuid(),
  source_entity_id uuid not null references entities(id) on delete cascade,
  target_entity_id uuid not null references entities(id) on delete cascade,
  relation_type text not null default 'related',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists relationships_source_idx on relationships (source_entity_id);
create index if not exists relationships_target_idx on relationships (target_entity_id);
create index if not exists relationships_source_target_idx on relationships (source_entity_id, target_entity_id);

-- ── Updated_at triggers ────────────────────────────────────────────────
create or replace function set_updated_at() returns trigger as $$
begin new.updated_at = now(); return new; end; $$ language plpgsql;

drop trigger if exists users_updated_at on users;
create trigger users_updated_at before update on users for each row execute function set_updated_at();
drop trigger if exists auth_sessions_updated_at on auth_sessions;
create trigger auth_sessions_updated_at before update on auth_sessions for each row execute function set_updated_at();
drop trigger if exists chat_sessions_updated_at on chat_sessions;
create trigger chat_sessions_updated_at before update on chat_sessions for each row execute function set_updated_at();
drop trigger if exists documents_updated_at on documents;
create trigger documents_updated_at before update on documents for each row execute function set_updated_at();
