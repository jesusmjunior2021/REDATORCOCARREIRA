#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/exporters.py — ETAPA 5: saida do documento.

  - .docx (ABNT-ish: Times 12, margens 3/2/2,5/2,5, justificado)
  - Google Docs no Drive, dentro da pasta "{MATRICULA} - {NOME}"
  - linha de log na planilha Google Sheets
  - historico local em JSON (memoria do agente)
  - perfil consolidado por servidor a cada 10 documentos
"""

from __future__ import annotations

import io
import json
import re
import datetime as dt
from pathlib import Path

from .keys import TZ

ESCOPOS = ["https://www.googleapis.com/auth/drive",
           "https://www.googleapis.com/auth/spreadsheets"]

CABECALHO_PLANILHA = ["data_hora", "tipologia", "modelos", "servidor", "matricula",
                      "assunto", "processo", "arquivo", "link", "campos_faltantes",
                      "provedores", "hash"]


# --------------------------------------------------------------------------- #
# NOMENCLATURA — busca semantica posterior
# --------------------------------------------------------------------------- #

def limpar(texto: str) -> str:
    texto = re.sub(r"\s+", " ", (texto or "").strip())
    texto = re.sub(r"[\\/:*?\"<>|]", "-", texto)
    return texto or "SEM-DADO"


def nome_pasta(matricula: str, nome: str) -> str:
    return f"{limpar(matricula)} - {limpar(nome).upper()}"


def nome_arquivo(matricula: str, nome: str, assunto: str, tipologia: str,
                 quando: dt.datetime | None = None) -> str:
    q = quando or dt.datetime.now(TZ)
    return (f"{limpar(matricula)}_{limpar(nome).upper()}_{limpar(assunto).upper()}"
            f"_{limpar(tipologia).upper()}_{q:%Y-%m-%d}")


# --------------------------------------------------------------------------- #
# DOCX
# --------------------------------------------------------------------------- #

def salvar_docx(texto: str, destino: Path) -> Path:
    from docx import Document
    from docx.shared import Pt, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()
    sec = doc.sections[0]
    sec.top_margin = Cm(3.0)
    sec.bottom_margin = Cm(2.0)
    sec.left_margin = Cm(3.0)
    sec.right_margin = Cm(2.0)

    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(12)

    for linha in texto.split("\n"):
        p = doc.add_paragraph(linha)
        pf = p.paragraph_format
        pf.space_after = Pt(6)
        pf.line_spacing = 1.5
        bruto = linha.strip()
        if bruto and bruto == bruto.upper() and len(bruto) < 60 and not bruto.startswith("|"):
            pf.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in p.runs:
                run.bold = True
        else:
            pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    destino.parent.mkdir(parents=True, exist_ok=True)
    doc.save(destino)
    return destino


# --------------------------------------------------------------------------- #
# GOOGLE
# --------------------------------------------------------------------------- #

def _servicos(sa_json: str | Path):
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_file(str(sa_json),
                                                                  scopes=ESCOPOS)
    return (build("drive", "v3", credentials=creds),
            build("sheets", "v4", credentials=creds))


def _pasta_do_servidor(drive, pasta_raiz: str, matricula: str, nome: str) -> str:
    alvo = nome_pasta(matricula, nome)
    q = (f"name = '{alvo}' and mimeType = 'application/vnd.google-apps.folder' "
         f"and '{pasta_raiz}' in parents and trashed = false")
    achados = drive.files().list(q=q, fields="files(id)", supportsAllDrives=True,
                                 includeItemsFromAllDrives=True).execute().get("files", [])
    if achados:
        return achados[0]["id"]
    criada = drive.files().create(
        body={"name": alvo, "mimeType": "application/vnd.google-apps.folder",
              "parents": [pasta_raiz]},
        fields="id", supportsAllDrives=True).execute()
    return criada["id"]


def enviar_google_docs(texto: str, sa_json: str | Path, pasta_raiz: str,
                       matricula: str, nome: str, assunto: str,
                       tipologia: str) -> dict:
    """Cria o Google Docs na pasta do servidor. Retorna {id, link, pasta, arquivo}."""
    from googleapiclient.http import MediaIoBaseUpload

    drive, _ = _servicos(sa_json)
    pasta_id = _pasta_do_servidor(drive, pasta_raiz, matricula, nome)
    arquivo = nome_arquivo(matricula, nome, assunto, tipologia)

    media = MediaIoBaseUpload(io.BytesIO(texto.encode("utf-8")),
                              mimetype="text/plain", resumable=False)
    criado = drive.files().create(
        body={"name": arquivo, "parents": [pasta_id],
              "mimeType": "application/vnd.google-apps.document"},
        media_body=media, fields="id, webViewLink",
        supportsAllDrives=True).execute()

    return {"id": criado["id"], "link": criado.get("webViewLink", ""),
            "pasta": nome_pasta(matricula, nome), "arquivo": arquivo}


def registrar_planilha(linha: list, sa_json: str | Path, planilha_id: str,
                       aba: str = "Documentos") -> None:
    _, sheets = _servicos(sa_json)
    intervalo = f"{aba}!A:L"
    atual = sheets.spreadsheets().values().get(
        spreadsheetId=planilha_id, range=f"{aba}!A1:L1").execute().get("values", [])
    if not atual:
        sheets.spreadsheets().values().update(
            spreadsheetId=planilha_id, range=f"{aba}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": [CABECALHO_PLANILHA]}).execute()
    sheets.spreadsheets().values().append(
        spreadsheetId=planilha_id, range=intervalo,
        valueInputOption="USER_ENTERED",
        body={"values": [linha]}).execute()


# --------------------------------------------------------------------------- #
# HISTORICO LOCAL E PERFIL
# --------------------------------------------------------------------------- #

def registrar_historico(entrada: dict, caminho: Path) -> list[dict]:
    hist: list[dict] = []
    if caminho.exists():
        try:
            hist = json.loads(caminho.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            hist = []
    hist.append(entrada)
    caminho.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")
    return hist


def consolidar_perfil(historico: list[dict], matricula: str,
                      destino_dir: Path) -> Path | None:
    """A cada 10 documentos do mesmo servidor, grava PERFIL_{MATRICULA}.md."""
    do_servidor = [h for h in historico if str(h.get("matricula")) == str(matricula)]
    if len(do_servidor) < 10 or len(do_servidor) % 10 != 0:
        return None

    nome = do_servidor[-1].get("servidor", "")
    linhas = [
        "---",
        f"name: perfil-{limpar(matricula)}",
        f"description: Perfil consolidado do servidor {nome} ({matricula})",
        "tipo: perfil_de_servidor",
        "---",
        "",
        f"# PERFIL — {nome} (matricula {matricula})",
        "",
        f"Documentos gerados: {len(do_servidor)}",
        "",
        "| Data | Tipologia | Assunto | Processo | Modelos |",
        "|---|---|---|---|---|",
    ]
    for h in do_servidor:
        linhas.append(
            f"| {h.get('data_hora','')[:10]} | {h.get('tipologia','')} | "
            f"{h.get('assunto','')} | {h.get('processo','')} | "
            f"{', '.join(h.get('modelos', []))} |")

    linhas += ["", "## ALERTAS DE INTERSTICIO",
               "Verificar antes de nova movimentacao:",
               "- 6 meses (art. 4o, par. unico, RESOL-GP-232010 c/ RESOL-GP-472011)",
               "- 2 anos (art. 1o, par. unico, RESOL-GP-432019)"]

    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / f"PERFIL_{limpar(matricula)}.md"
    destino.write_text("\n".join(linhas), encoding="utf-8")
    return destino
