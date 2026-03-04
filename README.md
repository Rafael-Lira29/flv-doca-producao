# 📦 App da Doca V31 - (Sistema Integrado FLV)

![Python](https://img.shields.io/badge/Python-3.11-blue?style=for-the-badge&logo=python)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white)
![Google Sheets API](https://img.shields.io/badge/Google_Sheets-34A853?style=for-the-badge&logo=google-sheets&logoColor=white)
![Status](https://img.shields.io/badge/Status-Produção-success?style=for-the-badge)

O **App da Doca V31** é uma solução de classe empresarial desenvolvida para digitalizar, otimizar e blindar o processo de recebimento de mercadorias (FLV - Frutas, Legumes e Verduras) no chão de loja do varejo. 

Construído para substituir pranchetas de papel por uma interface web móvel de altíssima resiliência, o sistema garante que a operação de contagem física seja exata e perfeitamente integrada com a Auditoria central (cruzamento com XMLs de Notas Fiscais).



---

## 🎯 O Problema que Resolvemos

No varejo de alto giro, o recebimento de perecíveis sofre com falhas de anotação, extravio de papéis e retrabalho na digitação. Isso gera uma divergência enorme entre o que foi **pedido**, o que foi **faturado (NFe)** e o que **entrou fisicamente**. 

O App da Doca elimina esse gargalo ao colocar uma ferramenta rápida e à prova de falhas na mão do conferente, enviando dados consolidados e limpos diretamente para o setor financeiro e de auditoria.

---

## ✨ Diferenciais e Inovações (Features)

* 🛡️ **Auto-Save (Rascunho Fantasma):** Motor de salvamento em milissegundos no banco de dados. Se o dispositivo do conferente perder a conexão ou a bateria acabar, nenhum dado é perdido.
* 👻 **Efeito Pac-Man (Poka-Yoke):** Limpeza automática da carga diária assim que a conferência é finalizada. Previne a duplicidade acidental de contagens pela equipe.
* ⚡ **Scroll Virtualizado:** Renderização de alta performance. Permite ao aplicativo lidar com listas gigantescas de produtos sem consumir a memória RAM do celular.
* 🧹 **Deduplicação Nativa:** O painel de histórico identifica múltiplos envios de correção e exporta para o CSV apenas a contagem consolidada e definitiva.
* 🔐 **Login Facilitado e Seguro:** Integração nativa com o *autocomplete* dos navegadores móveis (Chrome/Safari) combinada com gestão de acesso baseada em níveis de permissão (Admin/Operação).

---

## 🛠️ Stack Tecnológica

| Componente | Tecnologia Utilizada |
| :--- | :--- |
| **Linguagem Core** | Python 3.11 |
| **Front-end / Framework Web** | Streamlit |
| **Processamento e Transformação** | Pandas |
| **Banco de Dados (Real-time & Rascunhos)** | PostgreSQL (Neon) + SQLAlchemy |
| **Banco de Dados (Administrativo)** | Google Sheets API (`gspread`) |

---

💡 *Transformando dados físicos em inteligência digital de estoque.*
