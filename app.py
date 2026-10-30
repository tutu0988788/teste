import io
import time
import pandas as pd
import streamlit as st

from conferixml.processor import process_uploads

st.set_page_config(
    page_title="ConferiXML",
    page_icon="🧾",
    layout="wide"
)

# --------------------------------------------------
# CONFIGURAÇÕES DE SESSÃO
# --------------------------------------------------

TEMPO_EXPIRACAO = 15 * 60  # 15 minutos

if "last_activity" not in st.session_state:
    st.session_state.last_activity = time.time()

if "last_result" not in st.session_state:
    st.session_state.last_result = None

if "upload_generation" not in st.session_state:
    st.session_state.upload_generation = 0

# Expiração verificada em cada interação
agora = time.time()

if agora - st.session_state.last_activity > TEMPO_EXPIRACAO:
    st.session_state.last_result = None
    st.session_state.upload_generation += 1

st.session_state.last_activity = agora


def limpar_sessao():
    st.session_state.last_result = None
    st.session_state.upload_generation += 1
    st.session_state.last_activity = time.time()
    st.rerun()


# --------------------------------------------------
# VISUAL
# --------------------------------------------------

st.markdown("""
<style>
.block-container {
    padding-top: 1.4rem;
    max-width: 1400px;
}
.hero {
    padding: 1.3rem;
    border-radius: 14px;
    background: linear-gradient(110deg,#123c35,#176b52);
    color: white;
    margin-bottom: 1rem;
}
.hero h1 {
    margin: 0;
    font-size: 2rem;
}
.hero p {
    margin: .35rem 0 0 0;
    opacity: .85;
}
.small-muted {
    color: #777;
    font-size: .85rem;
}
</style>
""", unsafe_allow_html=True)


# --------------------------------------------------
# FUNÇÕES
# --------------------------------------------------

def brl(valor):
    return "R$ " + f"{float(valor or 0):,.2f}".replace(
        ",", "X"
    ).replace(".", ",").replace("X", ".")


def obter_resultado():
    return st.session_state.last_result


def documentos():
    result = obter_resultado()

    if result is None:
        return pd.DataFrame()

    return result["documents"]


# --------------------------------------------------
# MENU
# --------------------------------------------------

st.sidebar.title("🧾 ConferiXML")
st.sidebar.caption("Conferência de documentos fiscais")

page = st.sidebar.radio(
    "Navegação",
    [
        "Dashboard",
        "Nova análise",
        "Empresas",
        "Documentos",
        "Relatórios"
    ]
)

st.sidebar.divider()

st.sidebar.caption("Processamento temporário")
st.sidebar.caption("Sem histórico permanente")

if st.sidebar.button(
    "🔒 Encerrar sessão e limpar dados",
    use_container_width=True
):
    limpar_sessao()

st.sidebar.caption(
    "A sessão expira após 15 minutos de inatividade."
)


# --------------------------------------------------
# DASHBOARD
# --------------------------------------------------

if page == "Dashboard":

    st.markdown("""
    <div class="hero">
        <h1>ConferiXML</h1>
        <p>Conferência de faturamento a partir de XMLs fiscais</p>
    </div>
    """, unsafe_allow_html=True)

    result = obter_resultado()

    if result is None:
        st.info(
            "Nenhuma análise nesta sessão. "
            "Acesse Nova análise para começar."
        )

    else:
        summary = result["summary"]
        docs = result["documents"]

        valid = docs[
            docs["status_apuracao"] == "VÁLIDA"
        ] if not docs.empty else docs

        a, b, c, d = st.columns(4)

        a.metric(
            "Faturamento documental",
            brl(summary["faturamento"])
        )

        b.metric(
            "Pagamentos informados",
            brl(summary["pagamentos"])
        )

        c.metric(
            "Empresas identificadas",
            valid["cnpj_emitente"].nunique()
            if not valid.empty else 0
        )

        d.metric(
            "Documentos válidos",
            summary["validos"]
        )

        st.subheader("Faturamento por empresa")

        st.dataframe(
            result["by_company"],
            use_container_width=True,
            hide_index=True
        )


# --------------------------------------------------
# NOVA ANÁLISE
# --------------------------------------------------

elif page == "Nova análise":

    st.title("Nova análise")

    st.write(
        "Envie arquivos XML ou ZIP contendo documentos fiscais."
    )

    uploads = st.file_uploader(
        "Arquivos ZIP/XML",
        type=["zip", "xml"],
        accept_multiple_files=True,
        key=f"uploads_{st.session_state.upload_generation}"
    )

    st.caption(
        "O sistema separa automaticamente as empresas pelo CNPJ."
    )

    if st.button(
        "Processar arquivos",
        type="primary",
        disabled=not uploads
    ):

        with st.spinner("Processando documentos..."):

            try:
                result = process_uploads(uploads)

                st.session_state.last_result = result
                st.session_state.last_activity = time.time()

                st.success("Análise concluída!")

            except Exception:
                st.error(
                    "Não foi possível processar os arquivos. "
                    "Verifique os documentos enviados."
                )

    result = obter_resultado()

    if result is not None:

        summary = result["summary"]

        st.divider()
        st.subheader("Resultado da análise")

        a, b, c, d = st.columns(4)

        a.metric("XMLs encontrados", summary["xmls"])
        b.metric("Vendas válidas", summary["validos"])
        c.metric("Cancelados", summary["cancelados"])
        d.metric("Duplicados", summary["duplicados"])

        st.subheader("Resumo por empresa")

        st.dataframe(
            result["by_company"],
            use_container_width=True,
            hide_index=True
        )

        st.subheader("Conferências")

        st.write(
            f"**Faturamento documental:** "
            f"{brl(summary['faturamento'])}"
        )

        st.write(
            f"**Pagamentos informados:** "
            f"{brl(summary['pagamentos'])}"
        )

        st.write(
            f"**Diferença (vNF - vPag):** "
            f"{brl(summary['diferenca'])}"
        )

        if result["warnings"]:

            with st.expander(
                f"Avisos ({len(result['warnings'])})"
            ):

                for aviso in result["warnings"][:500]:
                    st.write("• " + aviso)

        docs = result["documents"]

        if not docs.empty:

            csv = docs.to_csv(
                index=False
            ).encode("utf-8-sig")

            st.download_button(
                "📥 Baixar documentos CSV",
                csv,
                "conferixml_documentos.csv",
                "text/csv"
            )


# --------------------------------------------------
# EMPRESAS
# --------------------------------------------------

elif page == "Empresas":

    st.title("Empresas")

    docs = documentos()

    if docs.empty:

        st.info("Nenhuma empresa identificada nesta sessão.")

    else:

        companies = docs.groupby(
            ["cnpj_emitente", "empresa"],
            dropna=False
        ).agg(
            documentos=("chave", "nunique"),
            faturamento=("valor_nf", "sum"),
            pagamentos=("valor_pago", "sum")
        ).reset_index()

        companies["faturamento"] = (
            companies["faturamento"].map(brl)
        )

        companies["pagamentos"] = (
            companies["pagamentos"].map(brl)
        )

        st.dataframe(
            companies,
            use_container_width=True,
            hide_index=True
        )


# --------------------------------------------------
# DOCUMENTOS
# --------------------------------------------------

elif page == "Documentos":

    st.title("Documentos")

    docs = documentos()

    if docs.empty:

        st.info("Nenhum documento nesta sessão.")

    else:

        c1, c2, c3 = st.columns(3)

        company_opts = [
            "Todas"
        ] + sorted(
            docs["empresa"].fillna(
                "Não identificada"
            ).unique().tolist()
        )

        company = c1.selectbox(
            "Empresa",
            company_opts
        )

        status = c2.selectbox(
            "Situação",
            ["Todas"] + sorted(
                docs["status_apuracao"].dropna().unique().tolist()
            )
        )

        model = c3.selectbox(
            "Modelo",
            ["Todos"] + sorted(
                docs["modelo"].dropna().unique().tolist()
            )
        )

        view = docs.copy()

        if company != "Todas":
            view = view[
                view["empresa"].fillna(
                    "Não identificada"
                ) == company
            ]

        if status != "Todas":
            view = view[
                view["status_apuracao"] == status
            ]

        if model != "Todos":
            view = view[
                view["modelo"] == model
            ]

        st.dataframe(
            view,
            use_container_width=True,
            hide_index=True
        )

        st.caption(
            f"{len(view)} documento(s) exibido(s)."
        )


# --------------------------------------------------
# RELATÓRIOS
# --------------------------------------------------

elif page == "Relatórios":

    st.title("Relatórios")

    docs = documentos()

    if docs.empty:

        st.info("Nenhum dado disponível nesta sessão.")

    else:

        valid = docs[
            docs["status_apuracao"] == "VÁLIDA"
        ].copy()

        if valid.empty:

            st.warning("Não há documentos válidos.")

        else:

            valid["data_emissao"] = pd.to_datetime(
                valid["data_emissao"],
                errors="coerce"
            )

            valid["dia"] = (
                valid["data_emissao"].dt.date.astype(str)
            )

            daily = valid.groupby(
                ["cnpj_emitente", "empresa", "dia"],
                dropna=False
            ).agg(
                quantidade=("chave", "nunique"),
                faturamento=("valor_nf", "sum"),
                pagamentos=("valor_pago", "sum")
            ).reset_index()

            company = valid.groupby(
                ["cnpj_emitente", "empresa"],
                dropna=False
            ).agg(
                quantidade=("chave", "nunique"),
                faturamento=("valor_nf", "sum"),
                pagamentos=("valor_pago", "sum")
            ).reset_index()

            st.subheader("Faturamento diário")

            st.dataframe(
                daily,
                use_container_width=True,
                hide_index=True
            )

            buffer = io.BytesIO()

            with pd.ExcelWriter(
                buffer,
                engine="openpyxl"
            ) as writer:

                company.to_excel(
                    writer,
                    sheet_name="Por empresa",
                    index=False
                )

                daily.to_excel(
                    writer,
                    sheet_name="Por dia",
                    index=False
                )

                docs.to_excel(
                    writer,
                    sheet_name="Documentos",
                    index=False
                )

            st.download_button(
                "📥 Exportar relatório Excel",
                buffer.getvalue(),
                "relatorio_conferixml.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
