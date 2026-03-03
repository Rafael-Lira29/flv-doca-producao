import streamlit as st
import pandas as pd
import gspread
import logging
from datetime import datetime, timedelta
from sqlalchemy import create_engine
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

# ================= 🔐 PORTA DO COORDENADOR ================= #
if menu == "🔐 Porta do Coordenador":
    st.title("⚙️ Gestão de Carga")
    senha = st.text_input("Senha:", type="password")
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
            usr, pwd = st.text_input("Usuário:"), st.text_input("Senha:", type="password")
            if st.form_submit_button("Entrar"):
                if "usuarios_doca" in st.secrets and usr in st.secrets["usuarios_doca"] and pwd == st.secrets["usuarios_doca"][usr][0]:
                    st.session_state.update({"usuario_logado": True, "loja_usuario": st.secrets["usuarios_doca"][usr][1], "nome_usuario": st.secrets["usuarios_doca"][usr][2], "hora_inicio": hora_brasil().strftime("%H:%M:%S")})
                    st.rerun()
                else: st.error("Acesso negado.")
    else:
        loja, nome = st.session_state.loja_usuario, st.session_state.nome_usuario
        st.info(f"👤 {nome} | 🏬 {loja} | ⏱️ Início: {st.session_state.hora_inicio}")
        
        df_carga = pd.DataFrame(sheet.worksheet(ABA_CARGA).get_all_records())
        df_loja = df_carga[df_carga["Loja"] == loja].copy()
        
        if df_loja.empty:
            st.success("Sem carga pendente.")
        else:
            try:
                df_temp = pd.DataFrame(sheet.worksheet(ABA_TEMP).get_all_records())
                if not df_temp.empty and "Loja" in df_temp.columns:
                    df_temp_loja = df_temp[df_temp["Loja"] == loja]
                else:
                    df_temp_loja = pd.DataFrame()
            except: df_temp_loja = pd.DataFrame()

            lista_final = []
            for _, item in df_loja.iterrows():
                if not df_temp_loja.empty and "Produto" in df_temp_loja.columns:
                    memoria = df_temp_loja[df_temp_loja["Produto"] == item["Produto"]]
                else:
                    memoria = pd.DataFrame()
                lista_final.append({
                    'Fornecedor': item['Fornecedor'],
                    'Produto': item['Produto'],
                    'Qtd_Recebida': float(memoria['Qtd_Recebida'].values[0]) if not memoria.empty else 0.0,
                    'Padrão_Cx': str(memoria['Padrão_Caixa_Kg'].values[0]) if not memoria.empty else "",
                    'Avaria': str(memoria['Avaria_Obs'].values[0]) if not memoria.empty else ""
                })
            
            df_editor = pd.DataFrame(lista_final)
            editado = st.data_editor(df_editor, disabled=["Fornecedor", "Produto"], hide_index=True, width='stretch')

            c1, c2 = st.columns(2)
            
            if c1.button("💾 SALVAR PROGRESSO"):
                with st.spinner("Guardando na memória..."):
                    ws_temp = sheet.worksheet(ABA_TEMP)
                    todos_temp = pd.DataFrame(ws_temp.get_all_records())
                    if not todos_temp.empty:
                        outras_lojas = todos_temp[todos_temp["Loja"] != loja]
                        ws_temp.clear()
                        if not outras_lojas.empty: ws_temp.update([outras_lojas.columns.values.tolist()] + outras_lojas.values.tolist())
                    
                    upload_temp = editado.copy()
                    upload_temp.insert(0, 'Loja', loja)
                    ws_temp.append_rows(upload_temp.values.tolist())
                    st.toast("Progresso salvo!")

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
                            logger.info(f"Gravado no Postgres com sucesso - Loja {loja}")
                        except Exception as e:
                            logger.error(f"Erro BD: {e}")
                            st.toast("Aviso: Falha no PostgreSQL, mas salvo na nuvem secundária!", icon="⚠️")

                    # Limpa a memória temporária
                    todos_temp = pd.DataFrame(sheet.worksheet(ABA_TEMP).get_all_records())
                    outras_lojas = todos_temp[todos_temp["Loja"] != loja]
                    sheet.worksheet(ABA_TEMP).clear()
                    if not outras_lojas.empty: sheet.worksheet(ABA_TEMP).update([outras_lojas.columns.values.tolist()] + outras_lojas.values.tolist())
                    
                    st.balloons()
                    st.success("Tudo pronto! Base de dados atualizada.")
                    st.session_state.usuario_logado = False

# ================= 📊 PAINEL DE REGISTROS ================= #
else:
    st.title("📊 Histórico")
    try:
        df_hist = pd.DataFrame(sheet.worksheet(ABA_CONTAGENS).get_all_records())
        st.dataframe(df_hist.tail(100), width='stretch')
    except: st.info("Sem registros.")
