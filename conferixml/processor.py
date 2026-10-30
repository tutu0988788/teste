import io
import zipfile
import xml.etree.ElementTree as ET
from pathlib import PurePosixPath
from decimal import Decimal, InvalidOperation
from datetime import datetime
import pandas as pd

NS = {"nfe": "http://www.portalfiscal.inf.br/nfe"}

def dec(value):
    try:
        return float(Decimal(str(value or "0").replace(",", ".")))
    except (InvalidOperation, ValueError):
        return 0.0

def local(tag):
    return tag.split("}")[-1] if "}" in tag else tag

def find_text(root, path):
    el = root.find(path, NS)
    return el.text.strip() if el is not None and el.text else ""

def iter_xml_uploads(uploads):
    for up in uploads:
        name = up.name
        raw = up.getvalue()
        if name.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as z:
                    for member in z.namelist():
                        if member.lower().endswith(".xml") and not member.endswith("/"):
                            try:
                                yield name + "/" + member, z.read(member)
                            except Exception:
                                continue
            except zipfile.BadZipFile:
                continue
        elif name.lower().endswith(".xml"):
            yield name, raw

def parse_payment(root):
    total = 0.0
    for el in root.iter():
        if local(el.tag) == "detPag":
            for child in el:
                if local(child.tag) == "vPag" and child.text:
                    total += dec(child.text)
    return total

def parse_xml(path, raw):
    try:
        root = ET.fromstring(raw)
    except Exception:
        return None, "XML inválido ou ilegível"
    tags = {local(x.tag) for x in root.iter()}
    if "procEventoNFe" in tags or "retEvento" in tags or "evento" in tags:
        ch = ""
        for el in root.iter():
            if local(el.tag) == "chNFe" and el.text:
                ch = el.text.strip()
                break
        tp = ""
        for el in root.iter():
            if local(el.tag) == "tpEvento" and el.text:
                tp = el.text.strip()
                break
        return {"tipo": "EVENTO", "chave_evento": ch, "tp_evento": tp, "path": path}, None

    inf = None
    for el in root.iter():
        if local(el.tag) == "infNFe":
            inf = el
            break
    if inf is None:
        return None, "Não é XML de NF-e/NFC-e processada"
    ide = next((x for x in inf if local(x.tag) == "ide"), None)
    emit = next((x for x in inf if local(x.tag) == "emit"), None)
    total = next((x for x in inf if local(x.tag) == "total"), None)
    prot = None
    for el in root.iter():
        if local(el.tag) == "protNFe":
            prot = el
            break
    chave = inf.attrib.get("Id", "").replace("NFe", "")
    if not chave and prot is not None:
        for el in prot.iter():
            if local(el.tag) == "chNFe" and el.text:
                chave = el.text.strip()
                break
    def child_text(parent, tag):
        if parent is None: return ""
        for x in parent.iter():
            if local(x.tag) == tag and x.text: return x.text.strip()
        return ""
    cnpj = child_text(emit, "CNPJ") or child_text(emit, "CPF")
    empresa = child_text(emit, "xNome") or "Empresa não identificada"
    modelo = child_text(ide, "mod")
    numero = child_text(ide, "nNF")
    serie = child_text(ide, "serie")
    dh = child_text(ide, "dhEmi") or child_text(ide, "dEmi")
    vnf = child_text(total, "vNF")
    # Somente XML processado/autorizado deve ser considerado venda válida.
    cstat = ""
    for el in root.iter():
        if local(el.tag) == "cStat" and el.text:
            cstat = el.text.strip()
    status = "VÁLIDA" if cstat in ("100", "150") else "NÃO AUTORIZADA"
    if "canc" in path.lower() or "evento" in path.lower() or "inu" in path.lower():
        status = "REVISAR PASTA"
    try:
        dt = datetime.fromisoformat(dh.replace("Z", "+00:00")).isoformat(sep=" ") if dh else ""
    except Exception:
        dt = dh
    return {
        "tipo": "VENDA", "chave": chave, "cnpj_emitente": cnpj, "empresa": empresa,
        "modelo": modelo, "numero": numero, "serie": serie, "data_emissao": dt,
        "valor_nf": dec(vnf), "valor_pago": parse_payment(root),
        "status_apuracao": status, "caminho": path
    }, None

def process_uploads(uploads):
    parsed = []
    warnings = []
    xml_count = 0
    events = []
    for path, raw in iter_xml_uploads(uploads):
        xml_count += 1
        item, err = parse_xml(path, raw)
        if err:
            warnings.append(f"{path}: {err}")
            continue
        if item["tipo"] == "EVENTO":
            events.append(item)
        else:
            # Arquivos em EVENTO/INU não são lançados como documentos de venda.
            lower = path.lower()
            if "/evento/" in lower or "/inu/" in lower or lower.startswith("evento/") or lower.startswith("inu/"):
                warnings.append(f"{path}: documento encontrado em pasta auxiliar; não somado automaticamente.")
                continue
            parsed.append(item)

    canceled_keys = set()
    for ev in events:
        if ev.get("tp_evento") == "110111" and ev.get("chave_evento"):
            canceled_keys.add(ev["chave_evento"])

    seen = set()
    duplicates = 0
    for d in parsed:
        key = d.get("chave")
        if key and key in seen:
            d["status_apuracao"] = "DUPLICADA"
            duplicates += 1
        elif key:
            seen.add(key)
        if key in canceled_keys:
            d["status_apuracao"] = "CANCELADA"

    df = pd.DataFrame(parsed)
    if df.empty:
        df = pd.DataFrame(columns=["chave","cnpj_emitente","empresa","modelo","numero","serie","data_emissao","valor_nf","valor_pago","status_apuracao","caminho"])
    valid = df[df["status_apuracao"] == "VÁLIDA"] if not df.empty else df
    faturamento = float(valid["valor_nf"].sum()) if not valid.empty else 0.0
    pagamentos = float(valid["valor_pago"].sum()) if not valid.empty else 0.0
    by = valid.groupby(["cnpj_emitente","empresa"], dropna=False).agg(
        documentos=("chave","nunique"), faturamento=("valor_nf","sum"), pagamentos=("valor_pago","sum")
    ).reset_index() if not valid.empty else pd.DataFrame(columns=["cnpj_emitente","empresa","documentos","faturamento","pagamentos"])
    summary = {
        "xmls": xml_count, "validos": len(valid),
        "cancelados": int((df["status_apuracao"] == "CANCELADA").sum()) if not df.empty else 0,
        "duplicados": duplicates, "faturamento": faturamento, "pagamentos": pagamentos,
        "diferenca": faturamento - pagamentos
    }
    return {"documents": df, "by_company": by, "summary": summary, "warnings": warnings}
