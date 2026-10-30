
import io
import zipfile
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from datetime import datetime
from pathlib import PurePosixPath

import pandas as pd


# Limites de segurança
MAX_UPLOAD_FILES = 30
MAX_UPLOAD_SIZE = 50 * 1024 * 1024
MAX_XML_SIZE = 10 * 1024 * 1024
MAX_TOTAL_XML_SIZE = 100 * 1024 * 1024
MAX_XML_COUNT = 5000
MAX_COMPRESSION_RATIO = 100

NS = {"nfe": "http://www.portalfiscal.inf.br/nfe"}

DOCUMENT_COLUMNS = [
    "chave", "cnpj_emitente", "empresa", "modelo", "numero",
    "serie", "data_emissao", "valor_nf", "valor_pago",
    "status_apuracao", "caminho"
]


def local(tag):
    if not isinstance(tag, str):
        return ""
    return tag.split("}")[-1] if "}" in tag else tag


def dec(value):
    try:
        return float(Decimal(str(value or "0").replace(",", ".")))
    except (InvalidOperation, ValueError, TypeError):
        return 0.0


def child(parent, name):
    if parent is None:
        return None
    return next((x for x in parent if local(x.tag) == name), None)


def text(parent, name):
    el = child(parent, name)
    return el.text.strip() if el is not None and el.text else ""


def descendant_text(parent, name):
    if parent is None:
        return ""
    for el in parent.iter():
        if local(el.tag) == name and el.text:
            return el.text.strip()
    return ""


def parse_payment(root):
    total = Decimal("0")

    for pag in root.iter():
        if local(pag.tag) != "pag":
            continue

        for det in pag:
            if local(det.tag) != "detPag":
                continue

            for value in det:
                if local(value.tag) == "vPag" and value.text:
                    try:
                        total += Decimal(value.text.strip())
                    except InvalidOperation:
                        pass

    return float(total)


def iter_xml_uploads(uploads, warnings):
    if len(uploads) > MAX_UPLOAD_FILES:
        warnings.append(
            f"Limite de {MAX_UPLOAD_FILES} arquivos por envio excedido."
        )
        return

    total_xml_size = 0
    xml_count = 0

    for upload in uploads:
        name = upload.name
        raw = upload.getvalue()

        if len(raw) > MAX_UPLOAD_SIZE:
            warnings.append(f"{name}: arquivo excede o limite de 50 MB.")
            continue

        if name.lower().endswith(".xml"):
            if len(raw) > MAX_XML_SIZE:
                warnings.append(f"{name}: XML excede o limite de 10 MB.")
                continue

            total_xml_size += len(raw)
            xml_count += 1

            if total_xml_size > MAX_TOTAL_XML_SIZE:
                warnings.append("Limite total de XMLs excedido.")
                return

            if xml_count > MAX_XML_COUNT:
                warnings.append("Limite de quantidade de XMLs excedido.")
                return

            yield name, raw

        elif name.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    for info in archive.infolist():
                        if info.is_dir():
                            continue

                        member = info.filename
                        path = PurePosixPath(member)

                        if (
                            path.is_absolute()
                            or ".." in path.parts
                            or "\\" in member
                        ):
                            warnings.append(
                                f"{name}/{member}: caminho suspeito ignorado."
                            )
                            continue

                        if not member.lower().endswith(".xml"):
                            continue

                        if info.file_size > MAX_XML_SIZE:
                            warnings.append(
                                f"{name}/{member}: XML excede 10 MB."
                            )
                            continue

                        if info.compress_size == 0 and info.file_size > 0:
                            warnings.append(
                                f"{name}/{member}: arquivo ZIP suspeito."
                            )
                            continue

                        if (
                            info.compress_size > 0
                            and info.file_size / info.compress_size
                            > MAX_COMPRESSION_RATIO
                        ):
                            warnings.append(
                                f"{name}/{member}: taxa de compressão suspeita."
                            )
                            continue

                        total_xml_size += info.file_size
                        xml_count += 1

                        if total_xml_size > MAX_TOTAL_XML_SIZE:
                            warnings.append("Limite total de XMLs excedido.")
                            return

                        if xml_count > MAX_XML_COUNT:
                            warnings.append(
                                "Limite de quantidade de XMLs excedido."
                            )
                            return

                        try:
                            with archive.open(info) as stream:
                                content = stream.read(MAX_XML_SIZE + 1)

                            if len(content) > MAX_XML_SIZE:
                                warnings.append(
                                    f"{name}/{member}: XML excede 10 MB."
                                )
                                continue

                            yield f"{name}/{member}", content

                        except Exception:
                            warnings.append(
                                f"{name}/{member}: não foi possível ler o XML."
                            )

            except zipfile.BadZipFile:
                warnings.append(f"{name}: arquivo ZIP inválido.")
            except Exception:
                warnings.append(f"{name}: erro ao ler arquivo ZIP.")


def parse_event(root, path):
    event = None
    returned = None

    for el in root.iter():
        if local(el.tag) == "infEvento":
            parent_tag = ""
            # Identifica se o infEvento pertence ao retorno ou ao evento enviado.
            for parent in root.iter():
                if el in list(parent):
                    parent_tag = local(parent.tag)
                    break

            if parent_tag == "retEvento":
                returned = el
            elif parent_tag == "evento":
                event = el

    if event is None:
        for el in root.iter():
            if local(el.tag) == "evento":
                event = el
                break

    if event is not None:
        ch = descendant_text(event, "chNFe")
        tp = descendant_text(event, "tpEvento")
    else:
        ch = ""
        tp = ""

    if returned is not None:
        cstat = descendant_text(returned, "cStat")
        motivo = descendant_text(returned, "xMotivo")
    else:
        cstat = ""
        motivo = ""

    return {
        "tipo": "EVENTO",
        "chave_evento": ch,
        "tp_evento": tp,
        "cstat_evento": cstat,
        "motivo_evento": motivo,
        "path": path
    }


def parse_inutilization(root):
    for el in root.iter():
        if local(el.tag) == "infInut":
            return {
                "tipo": "INUTILIZACAO",
                "cstat": descendant_text(root, "cStat"),
                "motivo": descendant_text(root, "xMotivo")
            }
    return None


def parse_xml(path, raw):
    if len(raw) > MAX_XML_SIZE:
        return None, "XML excede o limite de 10 MB"

    try:
        root = ET.fromstring(raw)
    except Exception:
        return None, "XML inválido ou ilegível"

    inutilization = parse_inutilization(root)
    if inutilization:
        return inutilization, None

    tags = {local(el.tag) for el in root.iter()}

    if "procEventoNFe" in tags or (
        "evento" in tags and "retEvento" in tags
    ):
        return parse_event(root, path), None

    inf = next(
        (el for el in root.iter() if local(el.tag) == "infNFe"),
        None
    )

    if inf is None:
        return None, "Não é XML de NF-e/NFC-e reconhecido"

    ide = child(inf, "ide")
    emit = child(inf, "emit")
    total = child(inf, "total")

    chave = inf.attrib.get("Id", "").replace("NFe", "")

    prot = next(
        (el for el in root.iter() if local(el.tag) == "protNFe"),
        None
    )
    inf_prot = child(prot, "infProt")

    chave_protocolo = text(inf_prot, "chNFe")
    cstat = text(inf_prot, "cStat")

    if not chave:
        chave = chave_protocolo

    cnpj = text(emit, "CNPJ") or text(emit, "CPF")
    empresa = text(emit, "xNome") or "Empresa não identificada"

    modelo = text(ide, "mod")
    numero = text(ide, "nNF")
    serie = text(ide, "serie")
    dh = text(ide, "dhEmi") or text(ide, "dEmi")
    vnf = descendant_text(total, "vNF")

    if not inf_prot:
        status = "SEM PROTOCOLO"
    elif chave and chave_protocolo and chave != chave_protocolo:
        status = "REVISAR"
    elif cstat in ("100", "150"):
        status = "VÁLIDA"
    else:
        status = "NÃO AUTORIZADA"

    if modelo not in ("55", "65"):
        status = "MODELO NÃO SUPORTADO"

    try:
        dt = (
            datetime.fromisoformat(dh.replace("Z", "+00:00"))
            .isoformat(sep=" ")
            if dh else ""
        )
    except Exception:
        dt = dh

    return {
        "tipo": "VENDA",
        "chave": chave,
        "cnpj_emitente": cnpj,
        "empresa": empresa,
        "modelo": modelo,
        "numero": numero,
        "serie": serie,
        "data_emissao": dt,
        "valor_nf": dec(vnf),
        "valor_pago": parse_payment(root),
        "status_apuracao": status,
        "caminho": path
    }, None


def process_uploads(uploads):
    parsed = []
    events = []
    warnings = []

    xml_count = 0

    for path, raw in iter_xml_uploads(uploads, warnings):
        xml_count += 1

        item, error = parse_xml(path, raw)

        if error:
            warnings.append(f"{path}: {error}")
            continue

        if item["tipo"] == "EVENTO":
            events.append(item)

        elif item["tipo"] == "INUTILIZACAO":
            warnings.append(
                f"{path}: inutilização identificada; não foi somada como venda."
            )

        else:
            lower = path.lower()

            if (
                "/evento/" in lower
                or "/inu/" in lower
                or lower.startswith("evento/")
                or lower.startswith("inu/")
            ):
                warnings.append(
                    f"{path}: arquivo em pasta auxiliar; não somado automaticamente."
                )
                continue

            parsed.append(item)

    # Só considera cancelamento quando o retorno do evento foi homologado.
    canceled_keys = set()

    for event in events:
        if event.get("tp_evento") != "110111":
            continue

        if event.get("cstat_evento") in ("135", "155"):
            if event.get("chave_evento"):
                canceled_keys.add(event["chave_evento"])
        else:
            warnings.append(
                f"{event.get('path')}: evento de cancelamento sem confirmação "
                f"de homologação (cStat: {event.get('cstat_evento') or 'ausente'})."
            )

    # Aplica cancelamentos antes da deduplicação.
    for document in parsed:
        if document.get("chave") in canceled_keys:
            document["status_apuracao"] = "CANCELADA"

    # Evita contar a mesma chave mais de uma vez.
    seen = {}
    duplicates = 0

    for document in parsed:
        key = document.get("chave")

        if not key:
            warnings.append(
                f"{document.get('caminho')}: documento sem chave de acesso."
            )
            continue

        if key in seen:
            document["status_apuracao"] = "DUPLICADA"
            duplicates += 1
        else:
            seen[key] = document

    df = pd.DataFrame(parsed, columns=DOCUMENT_COLUMNS)

    valid = (
        df[df["status_apuracao"] == "VÁLIDA"].copy()
        if not df.empty else df
    )

    faturamento = (
        float(valid["valor_nf"].sum()) if not valid.empty else 0.0
    )
    pagamentos = (
        float(valid["valor_pago"].sum()) if not valid.empty else 0.0
    )

    if not valid.empty:
        by = valid.groupby(
            ["cnpj_emitente", "empresa"], dropna=False
        ).agg(
            documentos=("chave", "nunique"),
            faturamento=("valor_nf", "sum"),
            pagamentos=("valor_pago", "sum")
        ).reset_index()
    else:
        by = pd.DataFrame(
            columns=[
                "cnpj_emitente", "empresa", "documentos",
                "faturamento", "pagamentos"
            ]
        )

    summary = {
        "xmls": xml_count,
        "validos": len(valid),
        "cancelados": (
            int((df["status_apuracao"] == "CANCELADA").sum())
            if not df.empty else 0
        ),
        "duplicados": duplicates,
        "faturamento": faturamento,
        "pagamentos": pagamentos,
        "diferenca": faturamento - pagamentos
    }

    return {
        "documents": df,
        "by_company": by,
        "summary": summary,
        "warnings": warnings
    }
