create table public.workspace_plans (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.pro_workspaces (id) on delete cascade,
  report_id uuid not null references public.decision_reports (id),
  squad_state_id uuid not null references public.squad_state_versions (id),
  version integer not null check (version > 0),
  lifecycle text not null check (
    lifecycle in ('active', 'stale', 'completed', 'superseded', 'abandoned')
  ),
  plan_data jsonb not null,
  stale_reasons jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  activated_at timestamptz not null default now(),
  stale_at timestamptz,
  completed_at timestamptz,
  superseded_at timestamptz,
  abandoned_at timestamptz,
  unique (workspace_id, version)
);

create unique index workspace_plans_one_active_idx
  on public.workspace_plans (workspace_id)
  where lifecycle = 'active';

create index workspace_plans_history_idx
  on public.workspace_plans (workspace_id, version desc);

alter table public.workspace_plans enable row level security;
revoke all on public.workspace_plans from anon, authenticated;

comment on table public.workspace_plans is
  'Versioned conditional three-Gameweek plans tied to immutable reports and squad states.';
comment on column public.workspace_plans.plan_data is
  'Deterministic plan contract; hidden reasoning and raw model responses are excluded.';
