import io
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

import pandas as pd
import plotly.express as px
import streamlit as st
from supabase import create_client, Client

st.set_page_config(page_title="MF Control", page_icon="⚡", layout="wide")

TIPOS_ACAO = ["LEVANTAMENTO", "PROSPECÇÃO", "VARREDURA"]
STATUS_ACAO = ["PROGRAMADO", "PRÉ-PROGRAMADO", "EXECUTADO", "REPROGRAMAR", "CANCELAR"]
PERFIS = ["admin", "supervisor", "prospector", "campo", "consulta"]
PERMISSOES_EDICAO = {"admin", "supervisor"}
PERMISSOES_PROSPECTOR = {"admin", "supervisor", "prospector"}
PERMISSOES_CAMPO = {"admin", "supervisor", "campo"}


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
        .metric-card {background:#f8fafc;border:1px solid #e2e8f0;border-radius:18px;padding:18px;}
        .big-title {font-size:34px;font-weight:800;color:#0f172a;margin-bottom:0px;}
        .subtle {color:#64748b;font-size:14px;}
        .ok {color:#16a34a;font-weight:700;}
        .warn {color:#f97316;font-weight:700;}
        .bad {color:#dc2626;font-weight:700;}
        </style>
        """,
        unsafe_allow_html=True,
    )


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
    return pd.DataFrame(res.data or [])


@st.cache_data(ttl=30)
def load_users():
    res = supabase.table("app_users").select("*").order("nome").execute()
    return pd.DataFrame(res.data or [])


def clear_cache():
    load_trafos.clear()
    load_acoes.clear()
    load_users.clear()


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
            ["Dashboard", "Trafos", "Ações", "Importar / Exportar", "Histórico", "Admin usuários"],
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
    if mes:
        out = out[out["data_programada"].astype(str).str.startswith(mes)]
    return out


def page_dashboard():
    st.markdown("<div class='big-title'>Dashboard</div>", unsafe_allow_html=True)
    df = load_acoes()
    if df.empty:
        st.info("Nenhuma ação cadastrada ainda.")
        return
    df["data_programada"] = pd.to_datetime(df["data_programada"], errors="coerce")
    df["mes"] = df["data_programada"].dt.strftime("%Y-%m")
    filt = apply_filters(df)
    today = pd.Timestamp(date.today())
    atrasados = filt[(filt["data_programada"] < today) & (~filt["status"].isin(["EXECUTADO", "CANCELAR"]))]
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Ações", len(filt))
    k2.metric("Executadas", int((filt["status"] == "EXECUTADO").sum()))
    k3.metric("Programadas", int((filt["status"].isin(["PROGRAMADO", "PRÉ-PROGRAMADO"])).sum()))
    k4.metric("Reprogramar", int((filt["status"] == "REPROGRAMAR").sum()))
    k5.metric("Atrasadas", len(atrasados))

    c1, c2 = st.columns(2)
    with c1:
        g = filt.groupby(["tipo_acao", "status"]).size().reset_index(name="qtd")
        fig = px.bar(g, x="tipo_acao", y="qtd", color="status", text="qtd", title="Ações por tipo e status")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        gm = filt.groupby(["mes", "tipo_acao"]).size().reset_index(name="qtd").sort_values("mes")
        fig2 = px.line(gm, x="mes", y="qtd", color="tipo_acao", markers=True, title="Evolução mensal")
        st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Base filtrada")
    st.dataframe(filt.sort_values("data_programada", ascending=False), use_container_width=True, hide_index=True)


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
                c4, c5 = st.columns(2)
                lat = c4.number_input("Latitude", value=0.0, format="%.8f")
                lon = c5.number_input("Longitude", value=0.0, format="%.8f")
                obs = st.text_area("Observação")
                ok = st.form_submit_button("Salvar trafo")
            if ok and med:
                try:
                    supabase.table("trafos").insert({
                        "medicao_fiscal": med.strip(), "regional": regional, "municipio": municipio,
                        "bairro": bairro, "latitude": None if lat == 0 else lat, "longitude": None if lon == 0 else lon,
                        "observacao": obs, "created_by": user.get("id")
                    }).execute()
                    clear_cache(); st.success("Trafo cadastrado."); st.rerun()
                except Exception as e:
                    st.error(f"Erro ao cadastrar: {e}")
    st.dataframe(df, use_container_width=True, hide_index=True)


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
                trafo_label = st.selectbox("Medição Fiscal / Trafo", list(labels.keys()), index = None,placeholder="Procure pela Medição Fiscal")
                tipo = st.selectbox("Tipo de ação", TIPOS_ACAO)
                data_prog = st.date_input("Data programada", value=date.today())
                status = st.selectbox("Status", STATUS_ACAO, index=0)
                c1, c2 = st.columns(2)
                responsavel = c1.text_input("Responsável / Prospector")
                equipe = c2.text_input("Equipe de campo")
                data_exec = st.date_input("Data de execução", value=None)
                gerar = False
                meses = 2
                if tipo == "VARREDURA":
                    c3, c4 = st.columns(2)
                    gerar = c3.checkbox("Gerar revisita automática ao executar", value=True)
                    meses = c4.number_input("Meses para revisita", min_value=1, max_value=24, value=2)
                obs = st.text_area("Observação")
                evidencia = st.text_input("Link de evidência")
                ok = st.form_submit_button("Salvar ação")
            if ok:
                try:
                    payload = {
                        "trafo_id": labels[trafo_label], "tipo_acao": tipo, "data_programada": str(data_prog),
                        "data_execucao": str(data_exec) if data_exec else None, "status": status,
                        "responsavel": responsavel, "equipe": equipe, "gerar_revisita": gerar,
                        "meses_revisita": int(meses), "observacao": obs, "evidencia_url": evidencia,
                        "created_by": user.get("id")
                    }
                    res = supabase.table("acoes").insert(payload).execute()
                    acao_id = res.data[0]["id"]
                    log_history(acao_id, user.get("id"), "criação", None, status, "Ação criada")
                    if tipo == "VARREDURA" and status == "EXECUTADO" and gerar:
                        nova_data = data_prog + relativedelta(months=int(meses))
                        supabase.table("acoes").insert({
                            "trafo_id": labels[trafo_label], "tipo_acao": "VARREDURA", "data_programada": str(nova_data),
                            "status": "PRÉ-PROGRAMADO", "responsavel": responsavel, "equipe": equipe,
                            "origem": "REVISITA", "acao_origem_id": acao_id, "meses_revisita": int(meses),
                            "observacao": f"Revisita automática gerada a partir da varredura de {data_prog}.",
                            "created_by": user.get("id")
                        }).execute()
                    clear_cache(); st.success("Ação cadastrada."); st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar ação: {e}")

    df = load_acoes()
    if df.empty:
        st.info("Nenhuma ação cadastrada.")
        return
    filt = apply_filters(df)
    st.dataframe(filt, use_container_width=True, hide_index=True)

    st.subheader("Atualizar status")
    ids = filt["id"].tolist()
    if not ids:
        return
    row_label = st.selectbox("Selecione a ação", [f"{r.medicao_fiscal} | {r.tipo_acao} | {r.data_programada} | {r.status}" for r in filt.itertuples()], index = None, placeholder = "Procure pela medição fiscal")
    idx = [f"{r.medicao_fiscal} | {r.tipo_acao} | {r.data_programada} | {r.status}" for r in filt.itertuples()].index(row_label)
    selected = filt.iloc[idx].to_dict()
    if not can_edit_action(user["perfil"], selected["tipo_acao"]):
        st.warning("Seu perfil não pode editar esta ação.")
        return
    with st.form("update_status"):
        novo_status = st.selectbox("Novo status", STATUS_ACAO, index=STATUS_ACAO.index(selected["status"]))
        data_execucao = st.date_input("Data execução", value=pd.to_datetime(selected.get("data_execucao")).date() if pd.notna(selected.get("data_execucao")) else date.today())
        obs_update = st.text_area("Observação da atualização")
        criar_revisita = False
        if selected["tipo_acao"] == "VARREDURA" and novo_status == "EXECUTADO":
            criar_revisita = st.checkbox("Criar revisita automática", value=bool(selected.get("gerar_revisita", True)))
        ok = st.form_submit_button("Atualizar")
    if ok:
        try:
            supabase.table("acoes").update({
                "status": novo_status,
                "data_execucao": str(data_execucao) if novo_status == "EXECUTADO" else selected.get("data_execucao"),
                "observacao": (selected.get("observacao") or "") + (f"\n{datetime.now():%d/%m/%Y %H:%M} - {obs_update}" if obs_update else "")
            }).eq("id", selected["id"]).execute()
            log_history(selected["id"], user.get("id"), "status", selected["status"], novo_status, obs_update)
            if selected["tipo_acao"] == "VARREDURA" and novo_status == "EXECUTADO" and criar_revisita:
                nova_data = data_execucao + relativedelta(months=int(selected.get("meses_revisita") or 2))
                supabase.table("acoes").insert({
                    "trafo_id": supabase.table("acoes").select("trafo_id").eq("id", selected["id"]).single().execute().data["trafo_id"],
                    "tipo_acao": "VARREDURA", "data_programada": str(nova_data), "status": "PRÉ-PROGRAMADO",
                    "responsavel": selected.get("responsavel"), "equipe": selected.get("equipe"), "origem": "REVISITA",
                    "acao_origem_id": selected["id"], "meses_revisita": int(selected.get("meses_revisita") or 2),
                    "observacao": f"Revisita automática gerada a partir da varredura executada em {data_execucao}.",
                    "created_by": user.get("id")
                }).execute()
            clear_cache(); st.success("Status atualizado."); st.rerun()
        except Exception as e:
            st.error(f"Erro ao atualizar: {e}")


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
    st.caption("Colunas esperadas: medicao_fiscal, regional, municipio, bairro, latitude, longitude, observacao")
    file = st.file_uploader("Arquivo Excel de trafos", type=["xlsx"], key="trafos_up")
    if file and st.button("Importar trafos"):
        df = pd.read_excel(file).fillna("")
        count = 0
        for _, r in df.iterrows():
            med = str(r.get("medicao_fiscal", "")).strip()
            if not med:
                continue
            payload = {k: (None if r.get(k, "") == "" else r.get(k)) for k in ["regional","municipio","bairro","latitude","longitude","observacao"]}
            payload["medicao_fiscal"] = med; payload["created_by"] = user.get("id")
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
            payload = {
                "trafo_id": map_trafos[med], "tipo_acao": str(r.get("tipo_acao", "")).upper(),
                "data_programada": str(pd.to_datetime(r.get("data_programada")).date()),
                "status": str(r.get("status", "PROGRAMADO")).upper(), "responsavel": r.get("responsavel", ""),
                "equipe": r.get("equipe", ""), "observacao": r.get("observacao", ""),
                "origem": "IMPORTAÇÃO", "created_by": user.get("id")
            }
            supabase.table("acoes").insert(payload).execute(); count += 1
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
    elif page == "Trafos": page_trafos(user)
    elif page == "Ações": page_acoes(user)
    elif page == "Importar / Exportar": page_import_export(user)
    elif page == "Histórico": page_historico()
    elif page == "Admin usuários": page_admin(user)


if __name__ == "__main__":
    main()
