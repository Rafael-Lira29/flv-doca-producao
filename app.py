import streamlit as st
import pandas as pd
import gspread
import logging
import json
import time
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# ==========================================================
# 🛠 CONFIGURAÇÃO DE LOGGING E AMBIENTE
# ==========================================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

st.set_page_config(page_title="Doca Definitiva - Enterprise", layout="wide", page_icon="📦")

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

# --- MOTOR DE FILA DE ESPERA (EVITA COLISÃO E ERRO 429 DO GOOGLE) ---
def tentar_google_sheets(funcao, max_tentativas=3):
    for tentativa in range(max_tentativas):
        try:
            return funcao()
        except Exception as e:
            if tentativa < max_tentativas - 1:
                tempo_espera = 2 ** tentativa # Espera 1s, depois 2s, depois 4s...
                logger.warning(f"Google Sheets ocupado. Tentando novamente em {tempo_espera}s...")
                time.sleep(tempo_espera)
            else:
                logger.error("Falha definitiva no Google Sheets após múltiplas tentativas.")
                raise e

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
        creds = dict(st.secrets["gcp_service_account"])
        creds["private_key"] = creds["private_key"].replace("\\n", "\n")
        client = gspread.service_account_from_dict(creds)
        sh_client = client.open(NOME_PLANILHA)
        if "DATABASE_URL" in st.secrets:
            db_eng = create_engine(st.secrets["DATABASE_URL"], pool_size=5, max_overflow=10, pool_pre_ping=True)
    except Exception as e:
        logger.error(f"Erro na infraestrutura: {e}")
        st.error("Erro técnico na conexão.")
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
                    
                    def atualizar_carga():
                        sheet.worksheet(ABA_CARGA).clear()
                        sheet.worksheet(ABA_CARGA).update([["Data","Loja","Fornecedor","Produto"]] + dados_finais)
                        sheet.worksheet(ABA_TEMP).clear()
                        
                    tentar_google_sheets(atualizar_carga)
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
        
        if "df_inicial" not in st.session_state:
            with st.spinner("Preparando a prancheta de contagem..."):
                def puxar_carga():
                    return pd.DataFrame(sheet.worksheet(ABA_CARGA).get_all_records())
                
                try:
                    df_carga = tentar_google_sheets(puxar_carga)
                    if not df_carga.empty and "Loja" in df_carga.columns:
                        df_loja = df_carga[df_carga["Loja"] == loja].copy()
                    else: df_loja = pd.DataFrame()
                except: df_loja = pd.DataFrame()
                
                if df_loja.empty:
                    st.session_state.df_inicial = pd.DataFrame()
                else:
                    draft_json = None
                    if db_engine:
                        try:
                            query_draft = text("SELECT dados_json FROM doca_rascunho WHERE conferente = :conf AND loja = :loja AND data_conferencia = :dt")
                            with db_engine.connect() as conn:
                                res = conn.execute(query_draft, {"conf": nome, "loja": loja, "dt": hora_brasil().date()}).fetchone()
                                if res: draft_json = json.loads(res[0])
                        except: pass

                    df_draft = pd.DataFrame(draft_json) if draft_json else pd.DataFrame()
                    
                    # ======================================================
                    # 🚀 ADEUS ITERROWS: VETORIZAÇÃO PANDAS NA VEIA
                    # ======================================================
                    base_df = df_loja[['Fornecedor', 'Produto']].copy()
                    
                    if not df_draft.empty and "Produto" in df_draft.columns:
                        # Faz o cruzamento (Merge) na velocidade da luz
                        merged = pd.merge(base_df, df_draft[['Produto', 'Qtd_Recebida', 'Padrão_Cx', 'Avaria']], on='Produto', how='left')
                        merged['Qtd_Recebida'] = pd.to_numeric(merged['Qtd_Recebida'], errors='coerce').fillna(0.0)
                        merged['Padrão_Cx'] = merged['Padrão_Cx'].fillna("").astype(str)
                        merged['Avaria'] = merged['Avaria'].fillna("").astype(str)
                        
                        # Resgata os Produtos Extras que não estavam na carga original
                        produtos_originais = base_df['Produto'].unique()
                        extras = df_draft[~df_draft['Produto'].isin(produtos_originais)].copy()
                        
                        if not extras.empty:
                            for col in ['Fornecedor', 'Qtd_Recebida', 'Padrão_Cx', 'Avaria']:
                                if col not in extras.columns:
                                    extras[col] = "EXTRA" if col == 'Fornecedor' else (0.0 if col == 'Qtd_Recebida' else "")
                            
                            extras = extras[['Fornecedor', 'Produto', 'Qtd_Recebida', 'Padrão_Cx', 'Avaria']]
                            extras['Qtd_Recebida'] = pd.to_numeric(extras['Qtd_Recebida'], errors='coerce').fillna(0.0)
                            extras['Padrão_Cx'] = extras['Padrão_Cx'].fillna("").astype(str)
                            extras['Avaria'] = extras['Avaria'].fillna("").astype(str)
                            final_df = pd.concat([merged, extras], ignore_index=True)
                        else:
                            final_df = merged
                    else:
                        final_df = base_df.copy()
                        final_df['Qtd_Recebida'] = 0.0
                        final_df['Padrão_Cx'] = ""
                        final_df['Avaria'] = ""
                        
                    # Limpeza de strings 'nan' perdidas
                    final_df['Padrão_Cx'] = final_df['Padrão_Cx'].replace(['nan', 'None', 'NaN'], "")
                    final_df['Avaria'] = final_df['Avaria'].replace(['nan', 'None', 'NaN'], "")
                    
                    st.session_state.df_inicial = final_df

        if st.session_state.df_inicial.empty:
            st.success("Tudo limpo! Sem carga pendente para hoje na sua doca.")
        else:
            editado = st.data_editor(st.session_state.df_inicial, disabled=["Fornecedor", "Produto"], hide_index=True, width='stretch', key="editor_doca")

            # --- AUTO-SAVE POSTGRESQL ---
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
                        logger.error(f"Erro silencioso no Auto-Save (Backstage): {e}")

            st.caption("☁️ Auto-Save ativado: Suas edições são salvas em tempo real no banco principal.")

            # --- ADICIONAR PRODUTO EXTRA (SOLUÇÃO PARA FLV DINÂMICO) ---
            with st.expander("➕ Adicionar Produto Não Planejado (Divergência)"):
                with st.form("form_extra"):
                    c_forn, c_prod = st.columns(2)
                    novo_forn = c_forn.text_input("Fornecedor (Opcional)")
                    novo_prod = c_prod.text_input("Nome do Produto Recebido")
                    c_qtd, c_pad = st.columns(2)
                    nova_qtd = c_qtd.number_input("Qtd Recebida", min_value=0.0, step=1.0)
                    novo_pad = c_pad.text_input("Padrão (Cx/Kg)")
                    
                    if st.form_submit_button("Inserir na Prancheta"):
                        if novo_prod:
                            novo_item = pd.DataFrame([{
                                'Fornecedor': novo_forn if novo_forn else "DESCONHECIDO", 
                                'Produto': f"⚠️ EXTRA: {novo_prod.upper()}", 
                                'Qtd_Recebida': nova_qtd, 
                                'Padrão_Cx': novo_pad, 
                                'Avaria': ""
                            }])
                            st.session_state.df_inicial = pd.concat([st.session_state.df_inicial, novo_item], ignore_index=True)
                            st.rerun()
                        else:
                            st.warning("Preencha o nome do produto.")

            if st.button("🏁 FINALIZAR CONFERÊNCIA"):
                with st.spinner("Limpando a doca e guardando os dados (Fila Inteligente ativada)..."):
                    hora_fim = hora_brasil().strftime("%H:%M:%S")
                    final = editado.copy()
                    
                    # ======================================================
                    # 🛡️ O ESCUDO DE CHUMBO NO POSTGRESQL (Tolerância Zero a Falhas)
                    # ======================================================
                    if db_engine:
                        try:
                            df_sql = final.copy()
                            df_sql = df_sql.rename(columns={"Produto": "codigo_produto", "Qtd_Recebida": "quantidade_conferida", "Avaria": "divergencia"})
                            df_sql["loja"], df_sql["conferente"], df_sql["data_hora"] = loja, nome, hora_brasil()
                            df_sql = df_sql[["codigo_produto", "quantidade_conferida", "divergencia", "loja", "conferente", "data_hora"]]
                            
                            with db_engine.begin() as conn:
                                df_sql.to_sql("itens_conferencia", conn, if_exists="append", index=False)
                                query_del = text("DELETE FROM doca_rascunho WHERE conferente = :conf AND loja = :loja AND data_conferencia = :dt")
                                conn.execute(query_del, {"conf": nome, "loja": loja, "dt": hora_brasil().date()})
                        except Exception as e:
                            logger.error(f"Erro CRÍTICO no PostgreSQL: {e}")
                            st.error("🚨 Falha de conexão com o Banco de Dados! Seus dados continuam a salvo na tela. Verifique a internet e clique em Finalizar novamente.")
                            st.stop() # Paralisa o aplicativo. Não deixa ele avançar para limpar a carga.
                    
                    # GRAVAÇÃO GOOGLE SHEETS COM MOTOR DE RETRY
                    final_sheets = final.copy()
                    final_sheets.insert(0, 'Conferente', nome)
                    final_sheets.insert(1, 'Hora_Fim', hora_fim)
                    final_sheets.insert(2, 'Hora_Inicio', st.session_state.hora_inicio)
                    final_sheets.insert(3, 'Data', hora_brasil().strftime("%d/%m/%Y"))
                    final_sheets.insert(4, 'Loja', loja)
                    
                    def salvar_historico():
                        sheet.worksheet(ABA_CONTAGENS).append_rows(final_sheets.values.tolist())
                    tentar_google_sheets(salvar_historico)

                    # O EFEITO PAC-MAN COM MOTOR DE RETRY (Anti-Colisão)
                    def limpar_carga():
                        todos_carga = pd.DataFrame(sheet.worksheet(ABA_CARGA).get_all_records())
                        sheet.worksheet(ABA_CARGA).clear()
                        if not todos_carga.empty and "Loja" in todos_carga.columns:
                            outras_cargas = todos_carga[todos_carga["Loja"] != loja]
                            if not outras_cargas.empty:
                                sheet.worksheet(ABA_CARGA).update([outras_cargas.columns.values.tolist()] + outras_cargas.values.tolist())
                            else:
                                sheet.worksheet(ABA_CARGA).update([["Data", "Loja", "Fornecedor", "Produto"]])
                        else:
                            sheet.worksheet(ABA_CARGA).update([["Data", "Loja", "Fornecedor", "Produto"]])
                    
                    tentar_google_sheets(limpar_carga)
                    
                    st.session_state.ultimo_rascunho_hash = None
                    if "df_inicial" in st.session_state: del st.session_state.df_inicial
                        
                    st.balloons()
                    st.success("Tudo pronto! Doca liberada e dados guardados com segurança.")
                    st.session_state.clear()
                    st.rerun()

# ================= 📊 PAINEL DE REGISTROS ================= #
else:
    st.title("📊 Painel de Registros (Consolidado)")
    try:
        df_hist = pd.DataFrame(sheet.worksheet(ABA_CONTAGENS).get_all_records())
        if not df_hist.empty and 'Data' in df_hist.columns:
            datas = df_hist['Data'].unique().tolist()
            datas.sort(key=lambda date: datetime.strptime(date, "%d/%m/%Y") if '/' in date else date, reverse=True)
            
            c1, c2 = st.columns([1, 3])
            data_selecionada = c1.selectbox("📅 Escolha a Data:", datas)
            
            df_dia = df_hist[df_hist['Data'] == data_selecionada].copy()
            df_consolidado = df_dia.drop_duplicates(subset=['Loja', 'Fornecedor', 'Produto'], keep='last')
            
            st.success(f"✨ Visão Consolidada: Mostrando as contagens definitivas do dia {data_selecionada}.")
            
            csv = df_consolidado.to_csv(index=False).encode('utf-8')
            st.download_button(label="📥 Baixar CSV Consolidado", data=csv, file_name=f"Contagens_Doca_{str(data_selecionada).replace('/', '-')}.csv", mime="text/csv")
            
            st.dataframe(df_consolidado, width='stretch', hide_index=True)
        else:
            st.info("Sem registros no momento.")
    except Exception as e: st.error(f"Erro: {e}")
