create table public.accounts (
  id uuid primary key references auth.users (id) on delete cascade,
  entitlement text not null default 'pro_beta' check (entitlement in ('pro_beta', 'pro')),
  created_at timestamptz not null default now()
);

create table public.pro_workspaces (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null unique references public.accounts (id) on delete cascade,
  current_squad_state_id uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.squad_state_versions (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.pro_workspaces (id) on delete cascade,
  version integer not null check (version > 0),
  team_id bigint not null check (team_id > 0),
  team_name text not null check (char_length(team_name) between 1 and 80),
  source_gameweek integer not null check (source_gameweek between 1 and 38),
  player_ids jsonb not null,
  players jsonb not null,
  squad_positions jsonb not null,
  changes jsonb not null default '[]'::jsonb,
  captain_id integer not null,
  vice_captain_id integer not null,
  bank_tenths integer not null check (bank_tenths between 0 and 200),
  free_transfers integer not null check (free_transfers between 0 and 5),
  risk_preference text not null check (risk_preference in ('safe', 'balanced', 'aggressive')),
  confirmed_at timestamptz not null,
  data_retrieved_at timestamptz not null,
  freshness_status text not null default 'confirmed' check (freshness_status in ('confirmed', 'stale')),
  created_at timestamptz not null default now(),
  unique (workspace_id, version)
);

alter table public.pro_workspaces
  add constraint pro_workspaces_current_state_fk
  foreign key (current_squad_state_id) references public.squad_state_versions (id);

create table public.conversations (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null unique references public.pro_workspaces (id) on delete cascade,
  title text not null check (char_length(title) between 1 and 120),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.workspace_messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations (id) on delete cascade,
  sequence integer not null check (sequence > 0),
  role text not null check (role in ('user', 'assistant')),
  content text not null check (char_length(content) between 1 and 10000),
  created_at timestamptz not null default now(),
  unique (conversation_id, sequence)
);

create table public.decision_reports (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations (id) on delete cascade,
  squad_state_id uuid not null references public.squad_state_versions (id),
  version integer not null check (version > 0),
  report_type text not null check (report_type in ('named_transfer')),
  question text not null check (char_length(question) between 3 and 500),
  assistant_message text not null check (char_length(assistant_message) between 1 and 10000),
  report_data jsonb not null,
  provider text not null,
  model text not null,
  created_at timestamptz not null,
  data_retrieved_at timestamptz not null,
  unique (conversation_id, version)
);

create index workspace_messages_conversation_created_idx
  on public.workspace_messages (conversation_id, sequence);
create index decision_reports_conversation_version_idx
  on public.decision_reports (conversation_id, version desc);

alter table public.accounts enable row level security;
alter table public.pro_workspaces enable row level security;
alter table public.squad_state_versions enable row level security;
alter table public.conversations enable row level security;
alter table public.workspace_messages enable row level security;
alter table public.decision_reports enable row level security;

revoke all on public.accounts from anon, authenticated;
revoke all on public.pro_workspaces from anon, authenticated;
revoke all on public.squad_state_versions from anon, authenticated;
revoke all on public.conversations from anon, authenticated;
revoke all on public.workspace_messages from anon, authenticated;
revoke all on public.decision_reports from anon, authenticated;

comment on table public.accounts is 'Minimal account and entitlement record; email remains owned by Supabase Auth.';
comment on table public.workspace_messages is 'Visible user and assistant messages only; hidden reasoning is never persisted.';
comment on column public.decision_reports.report_data is 'Versioned, grounded decision report; raw model/provider payloads are excluded.';
