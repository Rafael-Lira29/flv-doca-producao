import streamlit as st
import pandas as pd
import gspread
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

# ==========================================================
# 🔐 CONFIGURAÇÕES INICIAIS
# ==========================================================

st.set_page_config(
    page_title="Doca V29 - Enterprise",
    layout="wide",
    page_icon="📦"
)

logging.basicConfig(
    filename="doca.log",
    level=logging.ERROR,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

NOME_PLANILHA = "Banco_Doca_TomeLeve"
ABA_CARGA = "Carga_Diaria"
ABA_CONTAGENS = "Contagens"
ABA_TEMP = "Temporario"

SENHA_COORDENADOR = st.secrets["senha_coordenador"]

COLUNAS_CARGA = ["Data", "Loja", "Fornecedor", "Produto"]

COLUNAS_TEMP = [
    "Loja",
    "Fornecedor",
    "Produto",
    "Qtd_Recebida",
    "Padrão_Caixa_Kg",
    "Avaria_Obs"
]

COLUNAS_CONTAGENS = [
    "Conferente",
    "Hora_Fim",
    "Hora_Inicio",
    "Data",
    "Loja",
    "Fornecedor",
    "Produto",
    "Qtd_Recebida",
    "Padrão_Caixa_Kg",
    "Avaria_Obs"
]

# ==========================================================
# 🕒 UTILITÁRIOS
# ==========================================================

def hora_brasil():
    return datetime.now(ZoneInfo("America/Sao_Paulo"))

def garantir_aba(sheet, nome_aba, colunas):
    ws = sheet.worksheet(nome_aba)
    dados = ws.get_all_values()

    if not dados:
        ws.update([colunas])
        return pd.DataFrame(columns=colunas)

    df = pd.DataFrame(ws.get_all_records())

    if not all(col in df.columns for col in colunas):
        ws.clear()
        ws.update([colunas])
        return pd.DataFrame(columns=colunas)

    return df

# ==========================================================
# 🔌 CONEXÃO GOOGLE
# ==========================================================

@st.cache_resource
def conectar_google():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        client = gspread.service_account_from_dict(creds_dict)
        return client.open(NOME_PLANILHA)
    except Exception as e:
        logging.error(str(e))
        st.error("Erro ao conectar com banco de dados.")
        st.stop()

sheet = conectar_google()

ws_carga = sheet.worksheet(ABA_CARGA)
ws_temp = sheet.worksheet(ABA_TEMP)
ws_contagens = sheet.worksheet(ABA_CONTAGENS)

# ==========================================================
# 🧠 MEMÓRIA DE SESSÃO
# ==========================================================

if "usuario_logado" not in st.session_state:
    st.session_state.update({
        "usuario_logado": False,
        "loja_usuario": "",
        "nome_usuario": "",
        "hora_inicio": "",
        "finalizado": False
    })

# ==========================================================
# 🎛 MENU LATERAL
# ==========================================================

menu = st.sidebar.selectbox(
    "Navegação:",
    ["📱 Porta da Doca", "🔐 Porta do Coordenador", "📊 Painel de Registros"]
)

# ==========================================================
# 🔐 PORTA DO COORDENADOR
# ==========================================================

if menu == "🔐 Porta do Coordenador":

    st.title("⚙️ Gestão de Carga")
    senha = st.text_input("Senha:", type="password")

    if senha == SENHA_COORDENADOR:

        arquivo = st.file_uploader("Planilha Blindada", type=["xlsx"])

        if st.button("🚀 Disparar Carga") and arquivo:

            try:
                xl = pd.ExcelFile(arquivo)
                dados_finais = []

                for loja in [a for a in xl.sheet_names if "LOJA" in a.upper()]:
                    df_loja = pd.read_excel(arquivo, sheet_name=loja, header=1)
                    fornecedor_atual = "DESCONHECIDO"

                    for _, row in df_loja.iterrows():
                        codigo = str(row["Código"]).strip()

                        if codigo.upper().startswith("FORNECEDOR:"):
                            fornecedor_atual = codigo.replace("Fornecedor:", "").strip()

                        elif pd.notna(row["Código"]) and codigo != "" and "FORNECEDOR" not in codigo.upper():
                            dados_finais.append([
                                hora_brasil().strftime("%d/%m/%Y"),
                                loja,
                                fornecedor_atual,
                                str(row["Descrição"]).strip()
                            ])

                ws_carga.clear()
                ws_carga.update([COLUNAS_CARGA] + dados_finais)

                ws_temp.clear()
                ws_temp.update([COLUNAS_TEMP])

                st.success("Carga enviada com sucesso!")

            except Exception as e:
                logging.error(str(e))
                st.error("Erro ao processar planilha.")

# ==========================================================
# 📱 PORTA DA DOCA
# ==========================================================

elif menu == "📱 Porta da Doca":

    if not st.session_state.usuario_logado:

        with st.form("login"):
            usuario = st.text_input("Usuário:")
            senha = st.text_input("Senha:", type="password")

            if st.form_submit_button("Entrar"):

                usuarios = st.secrets.get("usuarios_doca", {})

                if usuario in usuarios and senha == usuarios[usuario][0]:

                    st.session_state.usuario_logado = True
                    st.session_state.loja_usuario = usuarios[usuario][1]
                    st.session_state.nome_usuario = usuarios[usuario][2]
                    st.session_state.hora_inicio = hora_brasil().strftime("%H:%M:%S")
                    st.session_state.finalizado = False

                    st.rerun()
                else:
                    st.error("Acesso negado.")

    else:

        loja = st.session_state.loja_usuario
        nome = st.session_state.nome_usuario

        st.info(f"👤 {nome} | 🏬 {loja} | ⏱ {st.session_state.hora_inicio}")

        df_carga = garantir_aba(sheet, ABA_CARGA, COLUNAS_CARGA)
        df_temp = garantir_aba(sheet, ABA_TEMP, COLUNAS_TEMP)

        df_loja = df_carga[df_carga["Loja"] == loja]

        if df_loja.empty:
            st.success("Sem carga pendente.")
        else:

            df_temp_loja = df_temp[df_temp["Loja"] == loja]

            lista_final = []

            for _, item in df_loja.iterrows():

                memoria = df_temp_loja[
                    df_temp_loja["Produto"] == item["Produto"]
                ]

                lista_final.append({
                    "Fornecedor": item["Fornecedor"],
                    "Produto": item["Produto"],
                    "Qtd_Recebida": float(memoria["Qtd_Recebida"].values[0]) if not memoria.empty else 0.0,
                    "Padrão_Caixa_Kg": memoria["Padrão_Caixa_Kg"].values[0] if not memoria.empty else "",
                    "Avaria_Obs": memoria["Avaria_Obs"].values[0] if not memoria.empty else ""
                })

            df_editor = pd.DataFrame(lista_final)

            editado = st.data_editor(
                df_editor,
                disabled=["Fornecedor", "Produto"],
                hide_index=True,
                use_container_width=True
            )

            editado["Qtd_Recebida"] = pd.to_numeric(
                editado["Qtd_Recebida"],
                errors="coerce"
            ).fillna(0)

            col1, col2 = st.columns(2)

            # ---------------- SALVAR PROGRESSO ----------------

            if col1.button("💾 SALVAR PROGRESSO"):

                try:
                    df_temp = df_temp[df_temp["Loja"] != loja]

                    novo_temp = editado.copy()
                    novo_temp.insert(0, "Loja", loja)

                    df_final = pd.concat([df_temp, novo_temp], ignore_index=True)

                    ws_temp.clear()
                    ws_temp.update([COLUNAS_TEMP] + df_final.values.tolist())

                    st.success("Progresso salvo!")

                except Exception as e:
                    logging.error(str(e))
                    st.error("Erro ao salvar progresso.")

            # ---------------- FINALIZAR ----------------

            if col2.button("🏁 FINALIZAR CONFERÊNCIA") and not st.session_state.finalizado:

                try:
                    st.session_state.finalizado = True

                    hora_fim = hora_brasil().strftime("%H:%M:%S")

                    final = editado.copy()

                    final.insert(0, "Conferente", nome)
                    final.insert(1, "Hora_Fim", hora_fim)
                    final.insert(2, "Hora_Inicio", st.session_state.hora_inicio)
                    final.insert(3, "Data", hora_brasil().strftime("%d/%m/%Y"))
                    final.insert(4, "Loja", loja)

                    ws_contagens.append_rows(final.values.tolist())

                    df_temp = df_temp[df_temp["Loja"] != loja]
                    ws_temp.clear()
                    ws_temp.update([COLUNAS_TEMP] + df_temp.values.tolist())

                    st.success("Conferência finalizada!")
                    st.session_state.usuario_logado = False
                    st.rerun()

                except Exception as e:
                    logging.error(str(e))
                    st.error("Erro ao finalizar conferência.")

# ==========================================================
# 📊 PAINEL DE REGISTROS
# ==========================================================

else:

    st.title("📊 Histórico")

    try:
        df_hist = garantir_aba(sheet, ABA_CONTAGENS, COLUNAS_CONTAGENS)
        st.dataframe(df_hist.tail(100), use_container_width=True)
    except Exception as e:
        logging.error(str(e))
        st.error("Erro ao carregar histórico.")
