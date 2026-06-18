-- MF Control - Atualização UX / Ciclo do Trafo
-- Execute este arquivo no Supabase SQL Editor para atualizar uma base já criada.
-- Esta versão remove decisões automáticas: próxima etapa e revisita só são criadas após confirmação do usuário no app.

begin;

drop view if exists public.vw_acoes_completa cascade;

alter table public.trafos add column if not exists prioridade text not null default 'MÉDIA';
alter table public.trafos add column if not exists prazo_limite date;
alter table public.trafos add column if not exists etapa_atual text not null default 'NOVO';

alter table public.acoes add column if not exists gerar_revisita boolean not null default false;
alter table public.acoes add column if not exists meses_revisita int not null default 2;
alter table public.acoes add column if not exists acao_origem_id uuid references public.acoes(id);

-- Remove constraints antigas de status/tipo/origem, se existirem.
alter table public.acoes drop constraint if exists acoes_status_check;
alter table public.acoes drop constraint if exists acoes_tipo_acao_check;
alter table public.acoes drop constraint if exists acoes_origem_check;
alter table public.trafos drop constraint if exists trafos_prioridade_check;
alter table public.trafos drop constraint if exists trafos_etapa_atual_check;

update public.acoes set status = 'CANCELADO' where status = 'CANCELAR';
update public.trafos set prioridade = 'MÉDIA' where prioridade is null or prioridade = '';
update public.trafos set etapa_atual = 'NOVO' where etapa_atual is null or etapa_atual = '';

alter table public.acoes add constraint acoes_status_check
check (status in ('PROGRAMADO','PRÉ-PROGRAMADO','EM EXECUÇÃO','EXECUTADO','REPROGRAMAR','CANCELADO','ENCERRADO','CANCELAR'));

alter table public.acoes add constraint acoes_tipo_acao_check
check (tipo_acao in ('LEVANTAMENTO','PROSPECÇÃO','VARREDURA'));

alter table public.acoes add constraint acoes_origem_check
check (origem in ('MANUAL','IMPORTAÇÃO','REVISITA'));

alter table public.trafos add constraint trafos_prioridade_check
check (prioridade in ('ALTA','MÉDIA','BAIXA'));

alter table public.trafos add constraint trafos_etapa_atual_check
check (etapa_atual in (
    'NOVO',
    'LEVANTAMENTO_PROGRAMADO','LEVANTAMENTO_EXECUTADO',
    'PROSPECCAO_PROGRAMADA','PROSPECCAO_EXECUTADA',
    'VARREDURA_PROGRAMADA','VARREDURA_EXECUTADA',
    'REVISITA_PROGRAMADA','REVISITA_EXECUTADA',
    'ENCERRADO'
));

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

commit;
