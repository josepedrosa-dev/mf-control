# MF Control — Programação e Ações da Medição Fiscal

Sistema web em **Streamlit + Supabase** para controlar ações de **Levantamento, Prospecção e Varredura** por transformador de Medição Fiscal.

## Recursos implementados

### MVP 1
- Login com Supabase Auth.
- Cadastro de trafos / medição fiscal.
- Cadastro de ações: Levantamento, Prospecção e Varredura.
- Status: Programado, Pré-programado, Executado, Reprogramar e Cancelar.
- Atualização de status por perfil.
- Revisita automática para varredura executada.
- Dashboard com indicadores e gráficos.
- Filtros por mês, regional, tipo e status.

### MVP 2
- Importação em massa por Excel.
- Exportação completa para Excel.
- Histórico de alterações.
- Perfis de usuário: admin, supervisor, prospector, campo e consulta.
- Tela administrativa de usuários.
- Painel de ações atrasadas.

## Arquitetura

```text
Usuário
  ↓
Streamlit Community Cloud
  ↓
Supabase Auth
  ↓
Supabase Postgres
```

## Estrutura do projeto

```text
mf_control_app/
├── app.py
├── requirements.txt
├── README.md
├── .gitignore
├── .streamlit/
│   ├── config.toml
│   └── secrets.example.toml
└── sql/
    └── 01_schema_supabase.sql
```

## Passo 1 — Criar projeto no Supabase

1. Acesse o Supabase.
2. Crie um novo projeto.
3. Abra **SQL Editor**.
4. Execute o arquivo:

```text
sql/01_schema_supabase.sql
```

## Passo 2 — Criar usuário no Supabase Auth

1. Vá em **Authentication > Users**.
2. Clique em **Add user**.
3. Cadastre e-mail e senha.
4. Marque o e-mail como confirmado, se necessário.

Depois, no SQL Editor, rode:

```sql
insert into public.app_users (nome, email, perfil, ativo)
values ('Administrador', 'seu.email@empresa.com', 'admin', true)
on conflict (email) do update set perfil = 'admin', ativo = true;
```

Use o mesmo e-mail criado no Supabase Auth.

## Passo 3 — Configurar secrets no Streamlit

No Streamlit Community Cloud, em **App settings > Secrets**, cadastre:

```toml
SUPABASE_URL = "https://SEU_PROJETO.supabase.co"
SUPABASE_ANON_KEY = "sua_anon_public_key"
```

Esses valores ficam em **Supabase > Project Settings > API**.

## Passo 4 — Subir no GitHub

1. Crie um repositório no GitHub.
2. Suba todos os arquivos desta pasta.
3. Não envie `.streamlit/secrets.toml` real. Use apenas `secrets.example.toml`.

Exemplo:

```bash
git init
git add .
git commit -m "MVP MF Control"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/mf-control.git
git push -u origin main
```

## Passo 5 — Deploy no Streamlit Community Cloud

1. Acesse Streamlit Community Cloud.
2. Clique em **New app**.
3. Selecione o repositório GitHub.
4. Main file path: `app.py`.
5. Configure os secrets.
6. Deploy.

## Modelo de Excel para importar trafos

Colunas esperadas:

```text
medicao_fiscal, regional, municipio, bairro, latitude, longitude, observacao
```

## Modelo de Excel para importar ações

Colunas esperadas:

```text
medicao_fiscal, tipo_acao, data_programada, status, responsavel, equipe, observacao
```

Valores aceitos:

```text
tipo_acao: LEVANTAMENTO, PROSPECÇÃO, VARREDURA
status: PROGRAMADO, PRÉ-PROGRAMADO, EXECUTADO, REPROGRAMAR, CANCELAR
```

## Observação importante de segurança

Este MVP usa RLS simples: qualquer usuário autenticado pode ler e gravar no banco. A restrição por perfil é feita dentro do app Streamlit.

Para ambiente corporativo definitivo, recomendo evoluir para:

- políticas RLS por perfil;
- logs obrigatórios para toda alteração;
- controle de permissões no banco;
- armazenamento de evidências no Supabase Storage;
- bloqueio de exclusões físicas.

## Próximas melhorias recomendadas

- Mapa dos trafos.
- Calendário visual de programação.
- Upload de fotos/evidências.
- Alertas de ações atrasadas.
- Priorização automática por perda/eficiência.
- Integração com Power BI.


## Atualização do fluxo Levantamento/Prospecção → Varredura

A tela **Ações > Atualizar status** agora possui o bloco **Próxima etapa**.

Quando uma ação do tipo **LEVANTAMENTO** ou **PROSPECÇÃO** for atualizada para **EXECUTADO**, o sistema pergunta se o usuário deseja **seguir para varredura**.

Se confirmado, o app cria automaticamente uma nova ação:

- tipo: `VARREDURA`;
- status: `PROGRAMADO`;
- vinculada à ação original por `acao_origem_id`;
- com responsável, equipe, data programada e observação definidos pelo usuário.

O sistema também evita duplicidade: se a ação já tiver uma varredura vinculada, não cria outra automaticamente.

Para projetos já publicados antes desta atualização, execute no Supabase o arquivo:

```text
sql/02_update_fluxo_varredura.sql
```
