# MF Control — Controle de Ações e Programação da Medição Fiscal

Aplicativo Streamlit + Supabase para controle de Levantamento, Prospecção, Varredura e Revisita por Medição Fiscal/Trafo.

## O que mudou nesta versão

Esta versão transforma o aplicativo em uma esteira por **ciclo do trafo**.

- Nenhuma próxima etapa é criada automaticamente.
- Ao concluir Levantamento, Prospecção ou Varredura, o app abre a tela **Decidir próxima etapa do trafo**.
- A Varredura só é criada se o usuário confirmar.
- A Revisita só é criada se o usuário confirmar.
- Foi adicionada a página **Timeline do trafo**.
- Foi adicionada a página **Meu trabalho**.
- Foram adicionados os campos `etapa_atual`, `prioridade` e `prazo_limite` na tabela de trafos.

## Fluxo operacional

### Levantamento executado

O usuário escolhe:

- Decidir depois
- Encerrar ciclo
- Programar Prospecção
- Programar Varredura

### Prospecção executada

O usuário escolhe:

- Decidir depois
- Encerrar ciclo
- Programar Varredura

### Varredura executada

O usuário escolhe:

- Decidir depois
- Encerrar ciclo
- Programar Revisita
- Reprogramar Varredura

### Revisita executada

O usuário escolhe:

- Decidir depois
- Encerrar ciclo
- Reprogramar Revisita

## Estrutura

```text
mf_control_app/
├── app.py
├── requirements.txt
├── README.md
├── .streamlit/
│   ├── config.toml
│   └── secrets.example.toml
├── sql/
│   ├── 01_schema_supabase.sql
│   ├── 02_update_fluxo_varredura.sql
│   └── 03_update_ciclo_trafo.sql
└── assets/
    ├── modelo_trafos.xlsx
    └── modelo_acoes.xlsx
```

## Instalação em projeto novo

1. Crie um projeto no Supabase.
2. Vá em **SQL Editor**.
3. Execute o arquivo:

```text
sql/01_schema_supabase.sql
```

4. Crie um usuário em **Authentication > Users**.
5. Cadastre o mesmo e-mail como admin:

```sql
insert into public.app_users (nome, email, perfil, ativo)
values ('Administrador', 'seu.email@empresa.com', 'admin', true)
on conflict (email) do update set perfil = 'admin', ativo = true;
```

## Atualização de projeto existente

Se você já tinha instalado uma versão anterior, execute apenas:

```text
sql/03_update_ciclo_trafo.sql
```

Esse script:

- adiciona `prioridade`, `prazo_limite` e `etapa_atual` em `trafos`;
- atualiza os status para incluir `EM EXECUÇÃO`, `CANCELADO` e `ENCERRADO`;
- recria a view `vw_acoes_completa`;
- mantém compatibilidade com status antigo `CANCELAR`.

## Configuração dos Secrets no Streamlit

No Streamlit Cloud, configure:

```toml
SUPABASE_URL = "https://SEU_PROJETO.supabase.co"
SUPABASE_ANON_KEY = "SUA_ANON_PUBLIC_KEY"
```

## Deploy no Streamlit Community Cloud

1. Suba estes arquivos para um repositório no GitHub.
2. No Streamlit Community Cloud, crie um novo app.
3. Selecione o repositório.
4. Main file: `app.py`.
5. Configure os secrets.
6. Clique em Deploy.

## Permissões

| Perfil | Acesso |
|---|---|
| admin | Tudo |
| supervisor | Cadastra, edita, importa e acompanha |
| prospector | Atualiza Levantamento e Prospecção |
| campo | Atualiza Varredura/Revisita |
| consulta | Apenas visualiza |

## Observação importante

O aplicativo faz controle de perfil na interface. Para um ambiente corporativo mais rígido, recomenda-se evoluir as políticas RLS do Supabase para validar o perfil diretamente no banco.
