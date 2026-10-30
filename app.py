import io
import os
import zipfile
from datetime import datetime
import pandas as pd
import streamlit as st

from conferixml.db import init_db, save_analysis, load_analyses, load_documents
from conferixml.processor import process_uploads

st.set_page_config(page_title="ConferiXML", page_icon="🧾", layout="wide")
init_db()

st.markdown("""
<style>
.block-container {padding-top: 1.4rem; max-width: 1400px;}
.hero {padding: 1.1rem 1.3rem; border-radius: 14px; background: linear-gradient(110deg,#123c35,#176b52); color: white; margin-bottom: 1rem;}
.hero h1 {margin:0; font-size:2rem;}
.hero p {margin:.35rem 0 0 0; opacity:.85;}
.small-muted {color:#777; font-size:.85rem;}
</style>
""", unsafe_allow_html=True)

st.sidebar.title("🧾 ConferiXML")
page = st.sidebar.radio("Navegação", ["Dashboard", "Nova análise", "Empresas", "Documentos", "Relatórios"])
st.sidebar.caption("Processamento local • NF-e 55 / NFC-e 65")
st.sidebar.divider()
st.sidebar.caption("Banco local: conferixml.db")

def brl(v):
    return "R$ " + f"{float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

if page == "Dashboard":
    st.markdown('<div class="hero"><h1>ConferiXML</h1><p>Conferência de faturamento a partir de XMLs fiscais</p></div>', unsafe_allow_html=True)
    analyses = load_analyses()
    docs = load_documents()
    valid = docs[docs["status_apuracao"] == "VÁLIDA"] if not docs.empty else docs
    total = valid["valor_nf"].sum() if not valid.empty else 0
    payments = valid["valor_pago"].sum() if not valid.empty else 0
    companies = valid["cnpj_emitente"].nunique() if not valid.empty else 0
    a,b,c,d = st.columns(4)
    a.metric("Faturamento documental", brl(total))
    b.metric("Pagamentos informados", brl(payments))
    c.metric("Empresas identificadas", int(companies))
    d.metric("Documentos válidos", len(valid))
    st.subheader("Últimas análises")
    if analyses.empty:
        st.info("Ainda não há análises. Acesse **Nova análise** para importar seus XMLs.")
    else:
        st.dataframe(analyses, use_container_width=True, hide_index=True)
    if not valid.empty:
        st.subheader("Faturamento por empresa")
        by = valid.groupby(["cnpj_emitente","empresa"], dropna=False).agg(documentos=("chave","nunique"), faturamento=("valor_nf","sum"), pagamentos=("valor_pago","sum")).reset_index()
        by["faturamento"] = by["faturamento"].map(brl)
        by["pagamentos"] = by["pagamentos"].map(brl)
        st.dataframe(by, use_container_width=True, hide_index=True)

elif page == "Nova análise":
    st.markdown("## Nova análise")
    st.write("Envie um ou mais arquivos ZIP ou XML. O sistema percorre subpastas automaticamente.")
    uploads = st.file_uploader("Arquivos ZIP/XML", type=["zip","xml"], accept_multiple_files=True)
    st.caption("Dica: você pode enviar ZIPs de várias empresas na mesma análise. O CNPJ do emitente será usado para separar as empresas.")
    if st.button("Processar arquivos", type="primary", disabled=not uploads):
        with st.spinner("Lendo documentos, eventos e pagamentos..."):
            result = process_uploads(uploads)
            analysis_id = save_analysis(result, [u.name for u in uploads])
        st.success(f"Análise concluída. Código: {analysis_id}")
        st.session_state["last_result"] = result
    result = st.session_state.get("last_result")
    if result:
        summary = result["summary"]
        x,y,z,w = st.columns(4)
        x.metric("XMLs encontrados", summary["xmls"])
        y.metric("Vendas válidas", summary["validos"])
        z.metric("Cancelados", summary["cancelados"])
        w.metric("Duplicados", summary["duplicados"])
        st.subheader("Resumo por empresa")
        st.dataframe(result["by_company"], use_container_width=True, hide_index=True)
        st.subheader("Conferências")
        st.write(f"**Faturamento documental:** {brl(summary['faturamento'])}")
        st.write(f"**Pagamentos informados:** {brl(summary['pagamentos'])}")
        st.write(f"**Diferença (vNF - vPag):** {brl(summary['diferenca'])}")
        if result["warnings"]:
            with st.expander(f"Avisos ({len(result['warnings'])})", expanded=False):
                for msg in result["warnings"][:500]:
                    st.write("• " + msg)
        if not result["documents"].empty:
            data = result["documents"].to_csv(index=False).encode("utf-8-sig")
            st.download_button("Baixar documentos CSV", data, "conferixml_documentos.csv", "text/csv")

elif page == "Empresas":
    st.markdown("## Empresas")
    docs = load_documents()
    if docs.empty:
        st.info("Importe XMLs para identificar as empresas.")
    else:
        companies = docs.groupby(["cnpj_emitente","empresa"], dropna=False).agg(
            documentos=("chave","nunique"), faturamento=("valor_nf","sum"), pagamentos=("valor_pago","sum")
        ).reset_index()
        companies["faturamento"] = companies["faturamento"].map(brl)
        companies["pagamentos"] = companies["pagamentos"].map(brl)
        st.dataframe(companies, use_container_width=True, hide_index=True)

elif page == "Documentos":
    st.markdown("## Documentos")
    docs = load_documents()
    if docs.empty:
        st.info("Nenhum documento armazenado.")
    else:
        c1,c2,c3 = st.columns(3)
        company_opts = ["Todas"] + sorted(docs["empresa"].fillna("Não identificada").unique().tolist())
        company = c1.selectbox("Empresa", company_opts)
        status = c2.selectbox("Situação", ["Todas"] + sorted(docs["status_apuracao"].dropna().unique().tolist()))
        model = c3.selectbox("Modelo", ["Todos"] + sorted(docs["modelo"].dropna().unique().tolist()))
        view = docs.copy()
        if company != "Todas": view = view[view["empresa"].fillna("Não identificada") == company]
        if status != "Todas": view = view[view["status_apuracao"] == status]
        if model != "Todos": view = view[view["modelo"] == model]
        st.dataframe(view, use_container_width=True, hide_index=True)
        st.caption(f"{len(view)} registro(s) exibido(s).")

elif page == "Relatórios":
    st.markdown("## Relatórios")
    docs = load_documents()
    if docs.empty:
        st.info("Ainda não há dados para exportar.")
    else:
        valid = docs[docs["status_apuracao"] == "VÁLIDA"].copy()
        if valid.empty:
            st.warning("Não há documentos válidos.")
        else:
            valid["data_emissao"] = pd.to_datetime(valid["data_emissao"], errors="coerce")
            valid["dia"] = valid["data_emissao"].dt.date.astype(str)
            daily = valid.groupby(["cnpj_emitente","empresa","dia"], dropna=False).agg(
                quantidade=("chave","nunique"), faturamento=("valor_nf","sum"), pagamentos=("valor_pago","sum")
            ).reset_index()
            company = valid.groupby(["cnpj_emitente","empresa"], dropna=False).agg(
                quantidade=("chave","nunique"), faturamento=("valor_nf","sum"), pagamentos=("valor_pago","sum")
            ).reset_index()
            st.subheader("Faturamento diário")
            st.dataframe(daily, use_container_width=True, hide_index=True)
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                company.to_excel(writer, sheet_name="Por empresa", index=False)
                daily.to_excel(writer, sheet_name="Por dia", index=False)
                docs.to_excel(writer, sheet_name="Documentos", index=False)
            st.download_button("📥 Exportar relatório Excel", buffer.getvalue(), "relatorio_conferixml.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
