import streamlit as st
import pandas as pd
import gspread
import logging
import json
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# ==========================================================
# 🛠 CONFIGURAÇÃO DE LOGGING E AMBIENTE
# ==========================================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

st.set_page_config(page_title="Doca V31 - Enterprise", layout="wide", page_icon="📦")

st.markdown("""
    <style>
    div.stButton > button:first-child {
        background-color: #002060; color: white; height: 3em; font-weight: bold; width: 100%; border-radius: 8px;
    }
    div.stButton > button:first-child:hover { background-color: #00133d; }
    </style>
""", unsafe_allow_html=True)

NOME_PLANILHA = "Banco_Doca_TomeLeve"
ABA_CARGA = "Carga_Diaria"
ABA_CONTAGENS = "Contagens"
ABA_TEMP = "Temporario"
SENHA_COORDENADOR = st.secrets["senha_coordenador"]

def hora_brasil():
    return datetime.utcnow() - timedelta(hours=3)

# --- MEMÓRIA DA SESSÃO ---
if "usuario_logado" not in st.session_state:
    st.session_state.update({"usuario_logado": False, "loja_usuario": "", "nome_usuario": "", "hora_inicio": ""})
if "ultimo_rascunho_hash" not in st.session_state:
    st.session_state.ultimo_rascunho_hash = None

# ==========================================================
# 🔌 CONEXÕES (SINGLETONS)
# ==========================================================
@st.cache_resource
def init_connections():
    sh_client, db_eng = None, None
    try:
        # 1. Google Sheets
        creds = dict(st.secrets["gcp_service_account"])
        creds["private_key"] = creds["private_key"].replace("\\n", "\n")
        client = gspread.service_account_from_dict(creds)
        sh_client = client.open(NOME_PLANILHA)
        
        # 2. PostgreSQL Enterprise
        if "DATABASE_URL" in st.secrets:
            db_eng = create_engine(
                st.secrets["DATABASE_URL"],
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True
            )
    except Exception as e:
        logger.error(f"Erro na infraestrutura: {e}")
        st.error("Erro técnico na conexão. A operar em modo de contingência.")
    
    return sh_client, db_eng

sheet, db_engine = init_connections()
if not sheet: st.stop()

# ---------------- MENU LATERAL ---------------- #
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/2830/2830305.png", width=80)
menu = st.sidebar.selectbox("Navegação:", ["📱 Porta da Doca", "🔐 Porta do Coordenador", "📊 Painel de Registros"])

if st.session_state.usuario_logado:
    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Sair (Logout)", type="secondary"):
        st.session_state.clear()
        st.rerun()

# ================= 🔐 PORTA DO COORDENADOR ================= #
if menu == "🔐 Porta do Coordenador":
    st.title("⚙️ Gestão de Carga")
    senha = st.text_input("Senha:", type="password", autocomplete="current-password")
    
    if senha == SENHA_COORDENADOR:
        arquivo = st.file_uploader("Planilha Blindada", type=["xlsx"])
        if st.button("🚀 Disparar Carga"):
            if arquivo:
                try:
                    xl = pd.ExcelFile(arquivo)
                    dados_finais = []
                    for loja in [a for a in xl.sheet_names if 'LOJA' in a.upper()]:
                        df_loja = pd.read_excel(arquivo, sheet_name=loja, header=1)
                        forn = "DESCONHECIDO"
                        for _, row in df_loja.iterrows():
                            cod = str(row['Código']).strip()
                            if cod.upper().startswith("FORNECEDOR:"): forn = cod.replace("Fornecedor:", "").strip()
                            elif pd.notna(row['Código']) and cod != "" and "FORNECEDOR" not in cod.upper():
                                dados_finais.append([hora_brasil().strftime("%d/%m/%Y"), loja, forn, str(row['Descrição']).strip()])
                    
                    sheet.worksheet(ABA_CARGA).clear()
                    sheet.worksheet(ABA_CARGA).update([["Data","Loja","Fornecedor","Produto"]] + dados_finais)
                    sheet.worksheet(ABA_TEMP).clear()
                    st.success("✅ Carga enviada para todas as unidades!")
                except Exception as e: st.error(e)

# ================= 📱 PORTA DA DOCA ================= #
elif menu == "📱 Porta da Doca":
    if not st.session_state.usuario_logado:
        with st.form("Login"):
            usr = st.text_input("Usuário:", autocomplete="username")
            pwd = st.text_input("Senha:", type="password", autocomplete="current-password")
            
            if st.form_submit_button("Entrar"):
                if "usuarios_doca" in st.secrets and usr in st.secrets["usuarios_doca"] and pwd == st.secrets["usuarios_doca"][usr][0]:
                    st.session_state.update({"usuario_logado": True, "loja_usuario": st.secrets["usuarios_doca"][usr][1], "nome_usuario": st.secrets["usuarios_doca"][usr][2], "hora_inicio": hora_brasil().strftime("%H:%M:%S")})
                    st.rerun()
                else: st.error("Acesso negado.")
    else:
        loja, nome = st.session_state.loja_usuario, st.session_state.nome_usuario
        st.info(f"👤 {nome} | 🏬 {loja} | ⏱️ Início: {st.session_state.hora_inicio}")
        
        # --- CARREGAMENTO ESTÁTICO (Só roda 1 vez ao fazer login) ---
        if "df_inicial" not in st.session_state:
            with st.spinner("Preparando a prancheta de contagem..."):
                df_carga = pd.DataFrame(sheet.worksheet(ABA_CARGA).get_all_records())
                df_loja = df_carga[df_carga["Loja"] == loja].copy()
                
                if df_loja.empty:
                    st.session_state.df_inicial = pd.DataFrame()
                else:
                    # Busca rascunho no banco de dados
                    draft_json = None
                    if db_engine:
                        try:
                            query_draft = text("SELECT dados_json FROM doca_rascunho WHERE conferente = :conf AND loja = :loja AND data_conferencia = :dt")
                            with db_engine.connect() as conn:
                                res = conn.execute(query_draft, {"conf": nome, "loja": loja, "dt": hora_brasil().date()}).fetchone()
                                if res: draft_json = json.loads(res[0])
                        except Exception as e:
                            logger.error(f"Erro ao carregar rascunho: {e}")

                    df_draft = pd.DataFrame(draft_json) if draft_json else pd.DataFrame()
                    if df_draft.empty:
                        try:
                            df_temp = pd.DataFrame(sheet.worksheet(ABA_TEMP).get_all_records())
                            if not df_temp.empty and "Loja" in df_temp.columns:
                                df_draft = df_temp[df_temp["Loja"] == loja]
                        except: pass

                    lista_final = []
                    for _, item in df_loja.iterrows():
                        memoria = pd.DataFrame()
                        if not df_draft.empty and "Produto" in df_draft.columns:
                            memoria = df_draft[df_draft["Produto"] == item["Produto"]]

                        qtd_rec = float(memoria['Qtd_Recebida'].values[0]) if not memoria.empty and 'Qtd_Recebida' in memoria.columns and pd.notna(memoria['Qtd_Recebida'].values[0]) else 0.0
                        
                        padrao = ""
                        if not memoria.empty:
                            val = memoria['Padrão_Cx'].values[0] if 'Padrão_Cx' in memoria.columns else (memoria['Padrão_Caixa_Kg'].values[0] if 'Padrão_Caixa_Kg' in memoria.columns else "")
                            if pd.notna(val) and str(val).lower() not in ["nan", "none"]: padrao = str(val)

                        avaria = ""
                        if not memoria.empty:
                            val = memoria['Avaria'].values[0] if 'Avaria' in memoria.columns else (memoria['Avaria_Obs'].values[0] if 'Avaria_Obs' in memoria.columns else "")
                            if pd.notna(val) and str(val).lower() not in ["nan", "none"]: avaria = str(val)

                        lista_final.append({
                            'Fornecedor': item['Fornecedor'],
                            'Produto': item['Produto'],
                            'Qtd_Recebida': qtd_rec,
                            'Padrão_Cx': padrao,
                            'Avaria': avaria
                        })
                    
                    st.session_state.df_inicial = pd.DataFrame(lista_final)

        # --- EXIBIÇÃO DA TABELA ---
        if st.session_state.df_inicial.empty:
            st.success("Sem carga pendente para hoje.")
        else:
            # A chave 'editor_doca' e o 'df_inicial' estático impedem que a tela pule!
            editado = st.data_editor(
                st.session_state.df_inicial, 
                disabled=["Fornecedor", "Produto"], 
                hide_index=True, 
                width='stretch',
                key="editor_doca"
            )

            # --- AUTO-SAVE INVISÍVEL (RASCUNHO FANTASMA) ---
            current_hash = hash(editado.to_string())
            if current_hash != st.session_state.ultimo_rascunho_hash:
                st.session_state.ultimo_rascunho_hash = current_hash
                if db_engine:
                    try:
                        json_data = editado.to_json(orient="records")
                        query_upsert = text("""
                            INSERT INTO doca_rascunho (conferente, loja, data_conferencia, dados_json)
                            VALUES (:conf, :loja, :dt, :json_data)
                            ON CONFLICT (conferente, loja, data_conferencia)
                            DO UPDATE SET dados_json = EXCLUDED.dados_json, ultima_atualizacao = CURRENT_TIMESTAMP;
                        """)
                        with db_engine.begin() as conn:
                            conn.execute(query_upsert, {"conf": nome, "loja": loja, "dt": hora_brasil().date(), "json_data": json_data})
                    except Exception as e:
                        logger.error(f"Erro no Auto-Save: {e}")

            st.caption("☁️ Auto-Save ativado: Suas edições são salvas sem interromper sua digitação.")

            c1, c2 = st.columns(2)
            
            if c1.button("💾 BACKUP NA PLANILHA (Opcional)"):
                with st.spinner("Guardando na aba temporária (Google Sheets)..."):
                    ws_temp = sheet.worksheet(ABA_TEMP)
                    todos_temp = pd.DataFrame(ws_temp.get_all_records())
                    ws_temp.clear()
                    
                    if not todos_temp.empty and "Loja" in todos_temp.columns:
                        outras_lojas = todos_temp[todos_temp["Loja"] != loja]
                        if not outras_lojas.empty: 
                            ws_temp.update([outras_lojas.columns.values.tolist()] + outras_lojas.values.tolist())
                    
                    upload_temp = editado.copy()
                    upload_temp.insert(0, 'Loja', loja)
                    ws_temp.append_rows(upload_temp.values.tolist())
                    st.toast("Backup secundário salvo na planilha!")

            if c2.button("🏁 FINALIZAR CONFERÊNCIA"):
                with st.spinner("A gravar no PostgreSQL e Sheets..."):
                    hora_fim = hora_brasil().strftime("%H:%M:%S")
                    final = editado.copy()
                    
                    # 1. GRAVAÇÃO GOOGLE SHEETS
                    final_sheets = final.copy()
                    final_sheets.insert(0, 'Conferente', nome)
                    final_sheets.insert(1, 'Hora_Fim', hora_fim)
                    final_sheets.insert(2, 'Hora_Inicio', st.session_state.hora_inicio)
                    final_sheets.insert(3, 'Data', hora_brasil().strftime("%d/%m/%Y"))
                    final_sheets.insert(4, 'Loja', loja)
                    sheet.worksheet(ABA_CONTAGENS).append_rows(final_sheets.values.tolist())
                    
                    # 2. GRAVAÇÃO POSTGRESQL (Nativo)
                    if db_engine:
                        try:
                            df_sql = final.copy()
                            df_sql = df_sql.rename(columns={
                                "Produto": "codigo_produto",
                                "Qtd_Recebida": "quantidade_conferida",
                                "Avaria": "divergencia"
                            })
                            df_sql["loja"] = loja
                            df_sql["conferente"] = nome
                            df_sql["data_hora"] = hora_brasil()
                            
                            colunas_bd = ["codigo_produto", "quantidade_conferida", "divergencia", "loja", "conferente", "data_hora"]
                            df_sql = df_sql[colunas_bd]
                            
                            with db_engine.begin() as conn:
                                df_sql.to_sql("itens_conferencia", conn, if_exists="append", index=False)
                                
                                # 3. LIMPEZA DO RASCUNHO FANTASMA DO BD
                                query_del = text("DELETE FROM doca_rascunho WHERE conferente = :conf AND loja = :loja AND data_conferencia = :dt")
                                conn.execute(query_del, {"conf": nome, "loja": loja, "dt": hora_brasil().date()})
                                
                            logger.info(f"Gravado no Postgres com sucesso - Loja {loja}")
                        except Exception as e:
                            logger.error(f"Erro BD: {e}")
                            st.toast("Aviso: Falha no PostgreSQL, mas salvo na nuvem secundária!", icon="⚠️")

                    # 4. LIMPEZA DA MEMÓRIA SECUNDÁRIA (Sheets e App)
                    todos_temp = pd.DataFrame(sheet.worksheet(ABA_TEMP).get_all_records())
                    sheet.worksheet(ABA_TEMP).clear()
                    if not todos_temp.empty and "Loja" in todos_temp.columns:
                        outras_lojas = todos_temp[todos_temp["Loja"] != loja]
                        if not outras_lojas.empty: 
                            sheet.worksheet(ABA_TEMP).update([outras_lojas.columns.values.tolist()] + outras_lojas.values.tolist())
                    
                    st.session_state.ultimo_rascunho_hash = None
                    st.balloons()
                    st.success("Tudo pronto! Base de dados atualizada.")
                    st.session_state.clear()
                    st.rerun()

# ================= 📊 PAINEL DE REGISTROS ================= #
else:
    st.title("📊 Histórico")
    try:
        df_hist = pd.DataFrame(sheet.worksheet(ABA_CONTAGENS).get_all_records())
        st.dataframe(df_hist.tail(100), width='stretch')
    except: st.info("Sem registros.")
