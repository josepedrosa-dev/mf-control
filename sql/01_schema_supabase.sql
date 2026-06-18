-- MF Control - Schema Supabase completo
-- Execute este arquivo no Supabase: SQL Editor > New Query > Run.

create extension if not exists "pgcrypto";

create table if not exists public.app_users (
    id uuid primary key default gen_random_uuid(),
    auth_user_id uuid unique,
    nome text not null,
    email text not null unique,
    perfil text not null default 'consulta' check (perfil in ('admin','supervisor','prospector','campo','consulta')),
    ativo boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.trafos (
    id uuid primary key default gen_random_uuid(),
    medicao_fiscal text not null unique,
    regional text,
    municipio text,
    bairro text,
    latitude numeric,
    longitude numeric,
    observacao text,
    prioridade text not null default 'MÉDIA' check (prioridade in ('ALTA','MÉDIA','BAIXA')),
    prazo_limite date,
    etapa_atual text not null default 'NOVO' check (etapa_atual in (
        'NOVO',
        'LEVANTAMENTO_PROGRAMADO','LEVANTAMENTO_EXECUTADO',
        'PROSPECCAO_PROGRAMADA','PROSPECCAO_EXECUTADA',
        'VARREDURA_PROGRAMADA','VARREDURA_EXECUTADA',
        'REVISITA_PROGRAMADA','REVISITA_EXECUTADA',
        'ENCERRADO'
    )),
    ativo boolean not null default true,
    created_by uuid references public.app_users(id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.acoes (
    id uuid primary key default gen_random_uuid(),
    trafo_id uuid not null references public.trafos(id) on delete cascade,
    tipo_acao text not null check (tipo_acao in ('LEVANTAMENTO','PROSPECÇÃO','VARREDURA')),
    data_programada date not null,
    data_execucao date,
    status text not null default 'PROGRAMADO' check (status in ('PROGRAMADO','PRÉ-PROGRAMADO','EM EXECUÇÃO','EXECUTADO','REPROGRAMAR','CANCELADO','ENCERRADO','CANCELAR')),
    responsavel text,
    equipe text,
    origem text not null default 'MANUAL' check (origem in ('MANUAL','IMPORTAÇÃO','REVISITA')),
    acao_origem_id uuid references public.acoes(id),
    gerar_revisita boolean not null default false,
    meses_revisita int not null default 2,
    observacao text,
    evidencia_url text,
    created_by uuid references public.app_users(id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.historico_acoes (
    id uuid primary key default gen_random_uuid(),
    acao_id uuid references public.acoes(id) on delete cascade,
    usuario_id uuid references public.app_users(id),
    campo text not null,
    valor_antigo text,
    valor_novo text,
    observacao text,
    created_at timestamptz not null default now()
);

create or replace function public.set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists trg_app_users_updated_at on public.app_users;
create trigger trg_app_users_updated_at before update on public.app_users
for each row execute function public.set_updated_at();

drop trigger if exists trg_trafos_updated_at on public.trafos;
create trigger trg_trafos_updated_at before update on public.trafos
for each row execute function public.set_updated_at();

drop trigger if exists trg_acoes_updated_at on public.acoes;
create trigger trg_acoes_updated_at before update on public.acoes
for each row execute function public.set_updated_at();

drop view if exists public.vw_acoes_completa cascade;
create view public.vw_acoes_completa as
select
    a.id,
    a.trafo_id,
    t.medicao_fiscal,
    t.regional,
    t.municipio,
    t.bairro,
    t.prioridade,
    t.prazo_limite,
    t.etapa_atual,
    a.tipo_acao,
    a.data_programada,
    a.data_execucao,
    case when a.status = 'CANCELAR' then 'CANCELADO' else a.status end as status,
    a.responsavel,
    a.equipe,
    a.origem,
    a.acao_origem_id,
    a.gerar_revisita,
    a.meses_revisita,
    a.observacao,
    a.evidencia_url,
    a.created_at,
    a.updated_at
from public.acoes a
join public.trafos t on t.id = a.trafo_id;

alter table public.app_users enable row level security;
alter table public.trafos enable row level security;
alter table public.acoes enable row level security;
alter table public.historico_acoes enable row level security;

create policy "auth read app_users" on public.app_users for select to authenticated using (true);
create policy "auth write app_users" on public.app_users for all to authenticated using (true) with check (true);

create policy "auth read trafos" on public.trafos for select to authenticated using (true);
create policy "auth write trafos" on public.trafos for all to authenticated using (true) with check (true);

create policy "auth read acoes" on public.acoes for select to authenticated using (true);
create policy "auth write acoes" on public.acoes for all to authenticated using (true) with check (true);

create policy "auth read historico" on public.historico_acoes for select to authenticated using (true);
create policy "auth write historico" on public.historico_acoes for all to authenticated using (true) with check (true);

-- Depois de criar o primeiro usuário no Supabase Auth, cadastre-o aqui como admin:
-- insert into public.app_users (nome, email, perfil, ativo)
-- values ('Seu Nome', 'seu.email@empresa.com', 'admin', true)
-- on conflict (email) do update set perfil = 'admin', ativo = true;
