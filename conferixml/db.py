import sqlite3
import json
import pandas as pd
from datetime import datetime

DB = "conferixml.db"

def conn():
    return sqlite3.connect(DB)

def init_db():
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            filenames TEXT,
            xmls INTEGER, validos INTEGER, cancelados INTEGER, duplicados INTEGER,
            faturamento REAL, pagamentos REAL
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_id INTEGER,
            chave TEXT,
            cnpj_emitente TEXT,
            empresa TEXT,
            modelo TEXT,
            numero TEXT,
            serie TEXT,
            data_emissao TEXT,
            valor_nf REAL,
            valor_pago REAL,
            status_apuracao TEXT,
            caminho TEXT,
            FOREIGN KEY(analysis_id) REFERENCES analyses(id)
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_doc_chave ON documents(chave)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_doc_empresa ON documents(cnpj_emitente)")

def save_analysis(result, filenames):
    with conn() as c:
        cur = c.execute("""INSERT INTO analyses
            (created_at,filenames,xmls,validos,cancelados,duplicados,faturamento,pagamentos)
            VALUES (?,?,?,?,?,?,?,?)""",
            (datetime.now().isoformat(timespec="seconds"), json.dumps(filenames, ensure_ascii=False),
             result["summary"]["xmls"], result["summary"]["validos"], result["summary"]["cancelados"],
             result["summary"]["duplicados"], result["summary"]["faturamento"], result["summary"]["pagamentos"]))
        aid = cur.lastrowid
        df = result["documents"].copy()
        if not df.empty:
            cols = ["chave","cnpj_emitente","empresa","modelo","numero","serie","data_emissao","valor_nf","valor_pago","status_apuracao","caminho"]
            df = df[cols].copy()
            df.insert(0, "analysis_id", aid)
            df.to_sql("documents", c, if_exists="append", index=False)
        return aid

def load_analyses():
    with conn() as c:
        return pd.read_sql_query("SELECT id AS análise, created_at AS data, filenames AS arquivos, xmls, validos, cancelados, duplicados, faturamento, pagamentos FROM analyses ORDER BY id DESC", c)

def load_documents():
    with conn() as c:
        return pd.read_sql_query("""SELECT d.chave,d.cnpj_emitente,d.empresa,d.modelo,d.numero,d.serie,d.data_emissao,
            d.valor_nf,d.valor_pago,d.status_apuracao,d.caminho,a.created_at AS analise
            FROM documents d LEFT JOIN analyses a ON a.id=d.analysis_id ORDER BY d.id DESC""", c)
