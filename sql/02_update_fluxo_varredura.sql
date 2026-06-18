-- MF Control - Atualização para fluxo Levantamento/Prospecção -> Varredura
-- Execute este arquivo no Supabase SQL Editor se seu projeto já foi criado com versão anterior.
-- Corrige/recria a view com campos necessários para vincular ações.

begin;

drop view if exists public.vw_acoes_completa cascade;

create view public.vw_acoes_completa as
select
    a.id,
    a.trafo_id,
    t.medicao_fiscal,
    t.regional,
    t.municipio,
    t.bairro,
    a.tipo_acao,
    a.data_programada,
    a.data_execucao,
    a.status,
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
