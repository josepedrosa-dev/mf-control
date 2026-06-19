import io
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

import pandas as pd
import plotly.express as px
import streamlit as st
from supabase import create_client, Client

st.set_page_config(page_title="MF Control", page_icon="⚡", layout="wide")

TIPOS_ACAO = ["LEVANTAMENTO", "PROSPECÇÃO", "VARREDURA"]
STATUS_ACAO = ["PROGRAMADO", "PRÉ-PROGRAMADO", "EM EXECUÇÃO", "EXECUTADO", "REPROGRAMAR", "CANCELADO", "ENCERRADO"]
STATUS_LEGADO = {"CANCELAR": "CANCELADO"}
PERFIS = ["admin", "supervisor", "prospector", "campo", "consulta"]
PERMISSOES_EDICAO = {"admin", "supervisor"}
PERMISSOES_PROSPECTOR = {"admin", "supervisor", "prospector"}
PERMISSOES_CAMPO = {"admin", "supervisor", "campo"}
PRIORIDADES = ["ALTA", "MÉDIA", "BAIXA"]
ETAPAS_TRAFO = [
    "NOVO", "LEVANTAMENTO_PROGRAMADO", "LEVANTAMENTO_EXECUTADO",
    "PROSPECCAO_PROGRAMADA", "PROSPECCAO_EXECUTADA",
    "VARREDURA_PROGRAMADA", "VARREDURA_EXECUTADA",
    "REVISITA_PROGRAMADA", "REVISITA_EXECUTADA", "ENCERRADO",
]


def get_secret(name: str) -> str:
    try:
        return st.secrets[name]
    except Exception:
        st.error(f"Configure o segredo {name} no Streamlit Cloud ou em .streamlit/secrets.toml.")
        st.stop()


@st.cache_resource
def get_supabase() -> Client:
    return create_client(get_secret("SUPABASE_URL"), get_secret("SUPABASE_ANON_KEY"))


supabase = get_supabase()


def sidebar_style():
    st.markdown(
        """
        <style>
        .big-title {font-size:34px;font-weight:800;color:#0f172a;margin-bottom:0px;}
        .subtle {color:#64748b;font-size:14px;}
        .pill {display:inline-block;border:1px solid #e2e8f0;border-radius:999px;padding:4px 10px;margin:2px;background:#f8fafc;font-size:13px;}
        .timeline {border-left:3px solid #cbd5e1;margin-left:12px;padding-left:18px;}
        .timeline-item {margin-bottom:16px;}
        .timeline-dot {width:14px;height:14px;background:#0f172a;border-radius:50%;display:inline-block;margin-left:-28px;margin-right:12px;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def normalize_status(status):
    return STATUS_LEGADO.get(status, status)


def login_screen():
    st.markdown("<div class='big-title'>MF Control</div>", unsafe_allow_html=True)
    st.caption("Controle de ações e programação da Medição Fiscal")
    with st.form("login"):
        email = st.text_input("E-mail")
        password = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Entrar", use_container_width=True)
    if submitted:
        try:
            auth = supabase.auth.sign_in_with_password({"email": email, "password": password})
            st.session_state["auth_user"] = auth.user
            st.session_state["email"] = email.lower().strip()
            st.rerun()
        except Exception as e:
            st.error("Login inválido ou usuário não cadastrado no Supabase Auth.")
            st.caption(str(e))


def get_current_user():
    email = st.session_state.get("email")
    if not email:
        return None
    res = supabase.table("app_users").select("*").eq("email", email).limit(1).execute()
    rows = res.data or []
    if rows:
        return rows[0]
    return {"id": None, "nome": email, "email": email, "perfil": "consulta", "ativo": False}


def require_login():
    if "auth_user" not in st.session_state:
        login_screen()
        st.stop()
    user = get_current_user()
    if not user or not user.get("ativo"):
        st.warning("Seu login existe no Supabase Auth, mas ainda não está ativo na tabela app_users.")
        st.info("Peça para um admin cadastrar seu e-mail em app_users e marcar ativo = true.")
        if st.button("Sair"):
            supabase.auth.sign_out()
            st.session_state.clear()
            st.rerun()
        st.stop()
    return user


def log_history(acao_id, user_id, campo, antigo, novo, obs=None):
    try:
        supabase.table("historico_acoes").insert({
            "acao_id": acao_id,
            "usuario_id": user_id,
            "campo": campo,
            "valor_antigo": None if antigo is None else str(antigo),
            "valor_novo": None if novo is None else str(novo),
            "observacao": obs,
        }).execute()
    except Exception:
        pass


@st.cache_data(ttl=30)
def load_trafos():
    res = supabase.table("trafos").select("*").order("medicao_fiscal").execute()
    return pd.DataFrame(res.data or [])


@st.cache_data(ttl=30)
def load_acoes():
    res = supabase.table("vw_acoes_completa").select("*").order("data_programada", desc=True).execute()
    df = pd.DataFrame(res.data or [])
    if not df.empty and "status" in df.columns:
        df["status"] = df["status"].map(normalize_status)
    return df


@st.cache_data(ttl=30)
def load_users():
    res = supabase.table("app_users").select("*").order("nome").execute()
    return pd.DataFrame(res.data or [])


def clear_cache():
    load_trafos.clear(); load_acoes.clear(); load_users.clear()


def get_acao_raw(acao_id):
    res = supabase.table("acoes").select("*").eq("id", acao_id).single().execute()
    return res.data


def get_acao_view(acao_id):
    res = supabase.table("vw_acoes_completa").select("*").eq("id", acao_id).limit(1).execute()
    rows = res.data or []
    if rows:
        rows[0]["status"] = normalize_status(rows[0].get("status"))
    return rows[0] if rows else None


def has_child_action(acao_id, tipo_acao=None, origem=None):
    query = supabase.table("acoes").select("id").eq("acao_origem_id", acao_id)
    if tipo_acao:
        query = query.eq("tipo_acao", tipo_acao)
    if origem:
        query = query.eq("origem", origem)
    res = query.limit(1).execute()
    return bool(res.data)


def derive_etapa(tipo_acao, status, origem=None):
    status = normalize_status(status)
    origem = origem or "MANUAL"
    if status in ["CANCELADO", "REPROGRAMAR"]:
        return None
    if status == "ENCERRADO":
        return "ENCERRADO"
    if tipo_acao == "LEVANTAMENTO":
        return "LEVANTAMENTO_EXECUTADO" if status == "EXECUTADO" else "LEVANTAMENTO_PROGRAMADO"
    if tipo_acao == "PROSPECÇÃO":
        return "PROSPECCAO_EXECUTADA" if status == "EXECUTADO" else "PROSPECCAO_PROGRAMADA"
    if tipo_acao == "VARREDURA" and origem == "REVISITA":
        return "REVISITA_EXECUTADA" if status == "EXECUTADO" else "REVISITA_PROGRAMADA"
    if tipo_acao == "VARREDURA":
        return "VARREDURA_EXECUTADA" if status == "EXECUTADO" else "VARREDURA_PROGRAMADA"
    return None


def update_trafo_etapa(trafo_id, etapa):
    if not etapa:
        return
    try:
        supabase.table("trafos").update({"etapa_atual": etapa}).eq("id", trafo_id).execute()
    except Exception:
        # Compatibilidade caso o usuário ainda não tenha executado o SQL de atualização.
        pass


def create_next_action(selected, user_id, tipo_acao, data_programada, responsavel="", equipe="", observacao="", origem="MANUAL"):
    raw = get_acao_raw(selected["id"])
    payload = {
        "trafo_id": raw["trafo_id"],
        "tipo_acao": tipo_acao,
        "data_programada": str(data_programada),
        "status": "PROGRAMADO" if origem != "REVISITA" else "PRÉ-PROGRAMADO",
        "responsavel": responsavel or selected.get("responsavel"),
        "equipe": equipe or selected.get("equipe"),
        "origem": origem,
        "acao_origem_id": selected["id"],
        "gerar_revisita": False,
        "meses_revisita": 2,
        "observacao": observacao,
        "created_by": user_id,
    }
    res = supabase.table("acoes").insert(payload).execute()
    nova_id = res.data[0]["id"]
    log_history(nova_id, user_id, "criação", None, payload["status"], f"Ação gerada a partir da ação {selected['id']}.")
    log_history(selected["id"], user_id, "próxima_etapa", selected.get("tipo_acao"), f"{tipo_acao}/{origem}", "Usuário escolheu a próxima etapa.")
    update_trafo_etapa(raw["trafo_id"], derive_etapa(tipo_acao, payload["status"], origem))
    return nova_id


def can_edit_action(user_perfil, tipo):
    if user_perfil in PERMISSOES_EDICAO:
        return True
    if tipo in ["LEVANTAMENTO", "PROSPECÇÃO"] and user_perfil in PERMISSOES_PROSPECTOR:
        return True
    if tipo == "VARREDURA" and user_perfil in PERMISSOES_CAMPO:
        return True
    return False


def sidebar(user):
    with st.sidebar:
        st.title("⚡ MF Control")
        st.caption(f"{user['nome']} · {user['perfil']}")
        page = st.radio(
            "Menu",
            ["Dashboard", "Meu trabalho", "Trafos", "Ações", "Timeline do trafo", "Importar / Exportar", "Histórico", "Admin usuários"],
        )
        if st.button("Atualizar dados", use_container_width=True):
            clear_cache(); st.rerun()
        if st.button("Sair", use_container_width=True):
            supabase.auth.sign_out(); st.session_state.clear(); st.rerun()
    return page


def apply_filters(df):
    if df.empty:
        return df
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        tipo = st.multiselect("Tipo de ação", TIPOS_ACAO, default=[])
    with c2:
        status = st.multiselect("Status", STATUS_ACAO, default=[])
    with c3:
        regional = st.multiselect("Regional", sorted(df.get("regional", pd.Series(dtype=str)).dropna().unique()), default=[])
    with c4:
        mes = st.text_input("Mês AAAA-MM", value="")
    out = df.copy()
    if tipo:
        out = out[out["tipo_acao"].isin(tipo)]
    if status:
        out = out[out["status"].isin(status)]
    if regional:
        out = out[out["regional"].isin(regional)]
    if mes and "data_programada" in out.columns:
        out = out[out["data_programada"].astype(str).str.startswith(mes)]
    return out


def page_dashboard():
    st.markdown("<div class='big-title'>Dashboard</div>", unsafe_allow_html=True)
    df = load_acoes()
    trafos = load_trafos()
    if df.empty:
        st.info("Nenhuma ação cadastrada ainda.")
        return
    df["data_programada"] = pd.to_datetime(df["data_programada"], errors="coerce")
    df["mes"] = df["data_programada"].dt.strftime("%Y-%m")
    filt = apply_filters(df)
    today = pd.Timestamp(date.today())
    atrasados = filt[(filt["data_programada"] < today) & (~filt["status"].isin(["EXECUTADO", "CANCELADO", "ENCERRADO"]))]

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Ações", len(filt))
    k2.metric("Executadas", int((filt["status"] == "EXECUTADO").sum()))
    k3.metric("Programadas", int((filt["status"].isin(["PROGRAMADO", "PRÉ-PROGRAMADO", "EM EXECUÇÃO"])).sum()))
    k4.metric("Reprogramar", int((filt["status"] == "REPROGRAMAR").sum()))
    k5.metric("Atrasadas", len(atrasados))

    if not trafos.empty and "etapa_atual" in trafos.columns:
        st.subheader("Pipeline por etapa atual do trafo")
        pipe = trafos.groupby("etapa_atual", dropna=False).size().reset_index(name="qtd")
        pipe["etapa_atual"] = pipe["etapa_atual"].fillna("SEM ETAPA")
        fig_pipe = px.bar(pipe, x="etapa_atual", y="qtd", text="qtd", title="Trafos por etapa atual")
        st.plotly_chart(fig_pipe, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        g = filt.groupby(["tipo_acao", "status"]).size().reset_index(name="qtd")
        fig = px.bar(g, x="tipo_acao", y="qtd", color="status", text="qtd", title="Ações por tipo e status")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        gm = filt.groupby(["mes", "tipo_acao"]).size().reset_index(name="qtd").sort_values("mes")
        fig2 = px.line(gm, x="mes", y="qtd", color="tipo_acao", markers=True, title="Evolução mensal")
        st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Atrasadas")
    st.dataframe(atrasados.sort_values("data_programada"), use_container_width=True, hide_index=True)
    st.subheader("Base filtrada")
    st.dataframe(filt.sort_values("data_programada", ascending=False), use_container_width=True, hide_index=True)


def page_meu_trabalho(user):
    st.markdown("<div class='big-title'>Meu trabalho</div>", unsafe_allow_html=True)
    df = load_acoes()
    if df.empty:
        st.info("Nenhuma ação cadastrada.")
        return
    email = user.get("email", "").lower()
    nome = user.get("nome", "").lower()
    if user["perfil"] in PERMISSOES_EDICAO:
        base = df.copy()
        st.caption("Perfil supervisor/admin: exibindo todas as ações abertas.")
    else:
        base = df[df.get("responsavel", pd.Series(dtype=str)).fillna("").str.lower().str.contains(nome, na=False) |
                  df.get("responsavel", pd.Series(dtype=str)).fillna("").str.lower().str.contains(email, na=False) |
                  df.get("equipe", pd.Series(dtype=str)).fillna("").str.lower().str.contains(nome, na=False)]
    abertas = base[~base["status"].isin(["EXECUTADO", "CANCELADO", "ENCERRADO"])]
    st.metric("Ações abertas", len(abertas))
    st.dataframe(abertas.sort_values("data_programada"), use_container_width=True, hide_index=True)


def page_trafos(user):
    st.markdown("<div class='big-title'>Trafos</div>", unsafe_allow_html=True)
    df = load_trafos()
    if user["perfil"] in PERMISSOES_EDICAO:
        with st.expander("Cadastrar novo trafo", expanded=False):
            with st.form("novo_trafo"):
                c1, c2, c3 = st.columns(3)
                med = c1.text_input("Medição Fiscal / Trafo *")
                regional = c2.text_input("Regional")
                municipio = c3.text_input("Município")
                bairro = st.text_input("Bairro")
                c4, c5, c6 = st.columns(3)
                lat = c4.number_input("Latitude", value=0.0, format="%.8f")
                lon = c5.number_input("Longitude", value=0.0, format="%.8f")
                prioridade = c6.selectbox("Prioridade", PRIORIDADES, index=1)
                prazo = st.date_input("Prazo limite", value=None)
                obs = st.text_area("Observação")
                ok = st.form_submit_button("Salvar trafo")
            if ok and med:
                try:
                    payload = {
                        "medicao_fiscal": med.strip(), "regional": regional, "municipio": municipio,
                        "bairro": bairro, "latitude": None if lat == 0 else lat, "longitude": None if lon == 0 else lon,
                        "observacao": obs, "created_by": user.get("id"),
                    }
                    # Campos novos. Caso o SQL de atualização ainda não tenha sido aplicado, o erro será exibido ao usuário.
                    payload.update({"prioridade": prioridade, "prazo_limite": str(prazo) if prazo else None, "etapa_atual": "NOVO"})
                    supabase.table("trafos").insert(payload).execute()
                    clear_cache(); st.success("Trafo cadastrado."); st.rerun()
                except Exception as e:
                    st.error(f"Erro ao cadastrar: {e}")
                    st.info("Se o erro mencionar prioridade, prazo_limite ou etapa_atual, execute o SQL sql/03_update_ciclo_trafo.sql no Supabase.")
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_proxima_etapa_pendente(user):
    pending_id = st.session_state.get("acao_proxima_etapa")
    if not pending_id:
        return
    selected = get_acao_view(pending_id)
    if not selected:
        st.session_state.pop("acao_proxima_etapa", None)
        return
    if selected.get("status") != "EXECUTADO":
        st.session_state.pop("acao_proxima_etapa", None)
        return

    st.divider()
    st.subheader("Decidir próxima etapa do trafo")
    st.info(f"A ação **{selected['tipo_acao']}** do trafo **{selected['medicao_fiscal']}** foi concluída. Escolha o próximo passo.")

    origem_atual = selected.get("origem") or "MANUAL"
    if selected["tipo_acao"] == "LEVANTAMENTO":
        opcoes = ["Decidir depois", "Encerrar ciclo", "Programar Prospecção", "Programar Varredura"]
    elif selected["tipo_acao"] == "PROSPECÇÃO":
        opcoes = ["Decidir depois", "Encerrar ciclo", "Programar Varredura"]
    else:
        if origem_atual == "REVISITA":
            opcoes = ["Decidir depois", "Encerrar ciclo", "Reprogramar Revisita"]
        else:
            opcoes = ["Decidir depois", "Encerrar ciclo", "Programar Revisita", "Reprogramar Varredura"]

    with st.form(f"form_proxima_etapa_{pending_id}"):
        decisao = st.radio("Próximo passo", opcoes, horizontal=False)
        c1, c2, c3 = st.columns(3)
        data_next = c1.date_input("Data programada", value=date.today() + relativedelta(months=2) if "Revisita" in decisao else date.today())
        responsavel = c2.text_input("Responsável", value=selected.get("responsavel") or "")
        equipe = c3.text_input("Equipe", value=selected.get("equipe") or "")
        obs = st.text_area("Observação", value="")
        confirmar = st.form_submit_button("Confirmar decisão", use_container_width=True)

    if confirmar:
        try:
            raw = get_acao_raw(selected["id"])
            if decisao == "Decidir depois":
                st.session_state.pop("acao_proxima_etapa", None)
                st.info("Nenhuma nova ação foi criada.")
                st.rerun()
            elif decisao == "Encerrar ciclo":
                update_trafo_etapa(raw["trafo_id"], "ENCERRADO")
                log_history(selected["id"], user.get("id"), "ciclo", selected.get("status"), "ENCERRADO", obs or "Ciclo encerrado pelo usuário.")
                st.session_state.pop("acao_proxima_etapa", None)
                clear_cache(); st.success("Ciclo do trafo encerrado."); st.rerun()
            elif decisao == "Programar Prospecção":
                if has_child_action(selected["id"], tipo_acao="PROSPECÇÃO"):
                    st.warning("Esta ação já possui prospecção vinculada.")
                else:
                    create_next_action(selected, user.get("id"), "PROSPECÇÃO", data_next, responsavel, equipe, obs or "Prospecção programada após levantamento.", "MANUAL")
                    st.success("Prospecção programada.")
                st.session_state.pop("acao_proxima_etapa", None); clear_cache(); st.rerun()
            elif decisao == "Programar Varredura":
                if has_child_action(selected["id"], tipo_acao="VARREDURA"):
                    st.warning("Esta ação já possui varredura vinculada.")
                else:
                    create_next_action(selected, user.get("id"), "VARREDURA", data_next, responsavel, equipe, obs or "Varredura programada após ação concluída.", "MANUAL")
                    st.success("Varredura programada.")
                st.session_state.pop("acao_proxima_etapa", None); clear_cache(); st.rerun()
            elif decisao == "Programar Revisita":
                if has_child_action(selected["id"], tipo_acao="VARREDURA", origem="REVISITA"):
                    st.warning("Esta varredura já possui revisita vinculada.")
                else:
                    create_next_action(selected, user.get("id"), "VARREDURA", data_next, responsavel, equipe, obs or "Revisita programada após varredura executada.", "REVISITA")
                    st.success("Revisita pré-programada.")
                st.session_state.pop("acao_proxima_etapa", None); clear_cache(); st.rerun()
            elif decisao in ["Reprogramar Varredura", "Reprogramar Revisita"]:
                origem = "REVISITA" if "Revisita" in decisao else "MANUAL"
                create_next_action(selected, user.get("id"), "VARREDURA", data_next, responsavel, equipe, obs or decisao, origem)
                st.session_state.pop("acao_proxima_etapa", None); clear_cache(); st.success("Nova programação criada."); st.rerun()
        except Exception as e:
            st.error(f"Erro ao aplicar decisão: {e}")


def page_acoes(user):
    st.markdown("<div class='big-title'>Ações</div>", unsafe_allow_html=True)
    trafos = load_trafos()
    if trafos.empty:
        st.warning("Cadastre pelo menos um trafo antes de criar ações.")
        return

    if user["perfil"] != "consulta":
        with st.expander("Cadastrar nova ação", expanded=True):
            labels = {f"{r['medicao_fiscal']} | {r.get('municipio') or ''} | {r.get('bairro') or ''}": r["id"] for _, r in trafos.iterrows()}
            with st.form("nova_acao"):
                trafo_label = st.selectbox("Medição Fiscal / Trafo", list(labels.keys()), input = None, placeholder = "Digite a medição fiscal")
                tipo = st.selectbox("Tipo de ação", TIPOS_ACAO)
                origem = "MANUAL"
                if tipo == "VARREDURA":
                    origem = st.selectbox("Origem da varredura", ["MANUAL", "REVISITA"], help="Use REVISITA apenas para uma nova visita após varredura executada.")
                data_prog = st.date_input("Data programada", value=date.today())
                status = st.selectbox("Status", STATUS_ACAO, index=0)
                c1, c2 = st.columns(2)
                responsavel = c1.text_input("Responsável / Prospector")
                equipe = c2.text_input("Equipe de campo")
                data_exec = st.date_input("Data de execução", value=None)
                obs = st.text_area("Observação")
                evidencia = st.text_input("Link de evidência")
                ok = st.form_submit_button("Salvar ação")
            if ok:
                try:
                    payload = {
                        "trafo_id": labels[trafo_label], "tipo_acao": tipo, "data_programada": str(data_prog),
                        "data_execucao": str(data_exec) if data_exec else None, "status": status,
                        "responsavel": responsavel, "equipe": equipe, "gerar_revisita": False,
                        "meses_revisita": 2, "observacao": obs, "evidencia_url": evidencia,
                        "origem": origem, "created_by": user.get("id")
                    }
                    res = supabase.table("acoes").insert(payload).execute()
                    acao_id = res.data[0]["id"]
                    log_history(acao_id, user.get("id"), "criação", None, status, "Ação criada")
                    update_trafo_etapa(labels[trafo_label], derive_etapa(tipo, status, origem))
                    if status == "EXECUTADO":
                        st.session_state["acao_proxima_etapa"] = acao_id
                    clear_cache(); st.success("Ação cadastrada."); st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar ação: {e}")

    df = load_acoes()
    if df.empty:
        st.info("Nenhuma ação cadastrada.")
        return
    filt = apply_filters(df)
    st.dataframe(filt, use_container_width=True, hide_index=True)

    render_proxima_etapa_pendente(user)

    st.subheader("Atualizar status")
    ids = filt["id"].tolist()
    if not ids:
        return
    labels_update = [f"{r.medicao_fiscal} | {r.tipo_acao} | {r.origem} | {r.data_programada} | {r.status}" for r in filt.itertuples()]
    row_label = st.selectbox("Selecione a ação", labels_update)
    idx = labels_update.index(row_label)
    selected = filt.iloc[idx].to_dict()
    if not can_edit_action(user["perfil"], selected["tipo_acao"]):
        st.warning("Seu perfil não pode editar esta ação.")
        return

    status_atual = normalize_status(selected["status"])
    index_status = STATUS_ACAO.index(status_atual) if status_atual in STATUS_ACAO else 0
    with st.form("update_status"):
        novo_status = st.selectbox("Novo status", STATUS_ACAO, index=index_status)
        data_execucao = st.date_input(
            "Data execução",
            value=pd.to_datetime(selected.get("data_execucao")).date() if pd.notna(selected.get("data_execucao")) else date.today(),
        )
        obs_update = st.text_area("Observação da atualização")
        if novo_status == "EXECUTADO":
            st.caption("Após salvar, o sistema abrirá a decisão da próxima etapa. Nada será criado automaticamente.")
        ok = st.form_submit_button("Atualizar")

    if ok:
        try:
            nova_obs = (selected.get("observacao") or "") + (f"\n{datetime.now():%d/%m/%Y %H:%M} - {obs_update}" if obs_update else "")
            raw = get_acao_raw(selected["id"])
            supabase.table("acoes").update({
                "status": novo_status,
                "data_execucao": str(data_execucao) if novo_status == "EXECUTADO" else selected.get("data_execucao"),
                "observacao": nova_obs,
            }).eq("id", selected["id"]).execute()
            log_history(selected["id"], user.get("id"), "status", selected["status"], novo_status, obs_update)
            update_trafo_etapa(raw["trafo_id"], derive_etapa(selected["tipo_acao"], novo_status, selected.get("origem")))
            if novo_status == "EXECUTADO":
                st.session_state["acao_proxima_etapa"] = selected["id"]
            else:
                st.session_state.pop("acao_proxima_etapa", None)
            clear_cache(); st.success("Status atualizado."); st.rerun()
        except Exception as e:
            st.error(f"Erro ao atualizar: {e}")


def page_timeline():
    st.markdown("<div class='big-title'>Timeline do trafo</div>", unsafe_allow_html=True)
    trafos = load_trafos()
    acoes = load_acoes()
    if trafos.empty:
        st.info("Nenhum trafo cadastrado.")
        return
    labels = {f"{r['medicao_fiscal']} | {r.get('municipio') or ''} | {r.get('bairro') or ''}": r["id"] for _, r in trafos.iterrows()}
    escolhido = st.selectbox("Selecione o trafo", list(labels.keys()))
    trafo_id = labels[escolhido]
    tr = trafos[trafos["id"] == trafo_id].iloc[0].to_dict()
    st.markdown(
        f"<span class='pill'>Etapa: {tr.get('etapa_atual', 'SEM ETAPA')}</span> "
        f"<span class='pill'>Prioridade: {tr.get('prioridade', '-')}</span> "
        f"<span class='pill'>Prazo: {tr.get('prazo_limite', '-')}</span>",
        unsafe_allow_html=True,
    )
    hist = acoes[acoes["trafo_id"] == trafo_id].copy()
    if hist.empty:
        st.info("Este trafo ainda não possui ações.")
        return
    hist["data_programada"] = pd.to_datetime(hist["data_programada"], errors="coerce")
    hist = hist.sort_values(["data_programada", "created_at"])
    st.markdown("<div class='timeline'>", unsafe_allow_html=True)
    for _, r in hist.iterrows():
        data_txt = r["data_programada"].strftime("%d/%m/%Y") if pd.notna(r["data_programada"]) else "sem data"
        titulo = "REVISITA" if r.get("origem") == "REVISITA" else r["tipo_acao"]
        st.markdown(
            f"<div class='timeline-item'><span class='timeline-dot'></span>"
            f"<b>{data_txt} · {titulo}</b><br>"
            f"Status: {r['status']} · Responsável: {r.get('responsavel') or '-'} · Equipe: {r.get('equipe') or '-'}<br>"
            f"<span class='subtle'>{r.get('observacao') or ''}</span></div>",
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)


def to_excel_bytes(dfs: dict) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name, df in dfs.items():
            df.to_excel(writer, index=False, sheet_name=name[:31])
    return output.getvalue()


def page_import_export(user):
    st.markdown("<div class='big-title'>Importar / Exportar</div>", unsafe_allow_html=True)
    acoes = load_acoes(); trafos = load_trafos()
    st.download_button(
        "Baixar base Excel",
        data=to_excel_bytes({"acoes": acoes, "trafos": trafos}),
        file_name=f"mf_control_export_{date.today()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    if user["perfil"] not in PERMISSOES_EDICAO:
        st.info("Importação disponível apenas para admin/supervisor.")
        return
    st.subheader("Importar trafos")
    st.caption("Colunas esperadas: medicao_fiscal, regional, municipio, bairro, latitude, longitude, observacao, prioridade, prazo_limite")
    file = st.file_uploader("Arquivo Excel de trafos", type=["xlsx"], key="trafos_up")
    if file and st.button("Importar trafos"):
        df = pd.read_excel(file).fillna("")
        count = 0
        for _, r in df.iterrows():
            med = str(r.get("medicao_fiscal", "")).strip()
            if not med:
                continue
            payload = {k: (None if r.get(k, "") == "" else r.get(k)) for k in ["regional","municipio","bairro","latitude","longitude","observacao","prioridade","prazo_limite"] if k in r.index}
            payload["medicao_fiscal"] = med; payload["created_by"] = user.get("id")
            payload.setdefault("etapa_atual", "NOVO")
            supabase.table("trafos").upsert(payload, on_conflict="medicao_fiscal").execute(); count += 1
        clear_cache(); st.success(f"{count} trafos importados/atualizados.")

    st.subheader("Importar ações")
    st.caption("Colunas esperadas: medicao_fiscal, tipo_acao, data_programada, status, responsavel, equipe, observacao")
    file2 = st.file_uploader("Arquivo Excel de ações", type=["xlsx"], key="acoes_up")
    if file2 and st.button("Importar ações"):
        base_trafos = load_trafos()
        map_trafos = dict(zip(base_trafos["medicao_fiscal"].astype(str), base_trafos["id"]))
        df = pd.read_excel(file2).fillna("")
        count = 0
        for _, r in df.iterrows():
            med = str(r.get("medicao_fiscal", "")).strip()
            if med not in map_trafos:
                continue
            tipo = str(r.get("tipo_acao", "")).upper()
            status = normalize_status(str(r.get("status", "PROGRAMADO")).upper())
            payload = {
                "trafo_id": map_trafos[med], "tipo_acao": tipo,
                "data_programada": str(pd.to_datetime(r.get("data_programada")).date()),
                "status": status, "responsavel": r.get("responsavel", ""),
                "equipe": r.get("equipe", ""), "observacao": r.get("observacao", ""),
                "origem": str(r.get("origem", "IMPORTAÇÃO")).upper() if r.get("origem", "") else "IMPORTAÇÃO", "created_by": user.get("id")
            }
            supabase.table("acoes").insert(payload).execute(); count += 1
            update_trafo_etapa(map_trafos[med], derive_etapa(tipo, status, payload["origem"]))
        clear_cache(); st.success(f"{count} ações importadas.")


def page_historico():
    st.markdown("<div class='big-title'>Histórico</div>", unsafe_allow_html=True)
    res = supabase.table("historico_acoes").select("*").order("created_at", desc=True).limit(1000).execute()
    st.dataframe(pd.DataFrame(res.data or []), use_container_width=True, hide_index=True)


def page_admin(user):
    st.markdown("<div class='big-title'>Admin usuários</div>", unsafe_allow_html=True)
    if user["perfil"] != "admin":
        st.warning("Apenas administradores podem acessar esta tela.")
        return
    with st.form("new_user"):
        c1, c2, c3 = st.columns(3)
        nome = c1.text_input("Nome")
        email = c2.text_input("E-mail")
        perfil = c3.selectbox("Perfil", PERFIS)
        ativo = st.checkbox("Ativo", value=True)
        ok = st.form_submit_button("Salvar usuário")
    if ok and email:
        supabase.table("app_users").upsert({"nome": nome or email, "email": email.lower().strip(), "perfil": perfil, "ativo": ativo}, on_conflict="email").execute()
        clear_cache(); st.success("Usuário salvo."); st.rerun()
    st.dataframe(load_users(), use_container_width=True, hide_index=True)


def main():
    sidebar_style()
    user = require_login()
    page = sidebar(user)
    if page == "Dashboard": page_dashboard()
    elif page == "Meu trabalho": page_meu_trabalho(user)
    elif page == "Trafos": page_trafos(user)
    elif page == "Ações": page_acoes(user)
    elif page == "Timeline do trafo": page_timeline()
    elif page == "Importar / Exportar": page_import_export(user)
    elif page == "Histórico": page_historico()
    elif page == "Admin usuários": page_admin(user)


if __name__ == "__main__":
    main()
