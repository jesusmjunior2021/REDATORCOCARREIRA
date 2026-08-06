#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/sheets.py — Planilha-banco no Google Drive.

Se a planilha nao existir, a aplicacao CRIA (botao "Criar planilha"), dentro da
pasta-raiz indicada, ja com as abas e os cabecalhos formatados. A partir dai cada
documento gerado alimenta uma linha com os dados reais, servindo de base de dados
consultavel no proprio Workspace.

Abas criadas:
  Documentos  — uma linha por peca expedida
  Servidores  — cadastro consolidado, com contagem e ultima movimentacao
  Lacunas     — auditoria dos campos que faltaram em cada peca
"""

from __future__ import annotations

import datetime as dt

from .keys import TZ

ESCOPOS = ["https://www.googleapis.com/auth/drive",
           "https://www.googleapis.com/auth/spreadsheets"]

ABAS: dict[str, list[str]] = {
    "Documentos": [
        "data_hora", "doc_id", "tipologia", "materia", "modelos", "servidor",
        "matricula", "assunto", "processo", "status", "versao", "completude_%",
        "campos_faltantes", "arquivo", "link_drive", "provedores", "hash",
    ],
    "Servidores": [
        "matricula", "nome", "cargo", "unidade", "qtd_documentos",
        "ultima_movimentacao", "atualizado_em", "observacoes",
    ],
    "Lacunas": [
        "data_hora", "doc_id", "servidor", "matricula", "campo",
        "pista", "resolvido_por", "observacao",
    ],
}

TITULO_PADRAO = "BASE DE DOCUMENTOS — COCARREIRA/CAEDNC"


# --------------------------------------------------------------------------- #
# SERVICOS
# --------------------------------------------------------------------------- #

def _servicos(sa_json: str):
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_file(
        str(sa_json), scopes=ESCOPOS)
    return (build("drive", "v3", credentials=creds),
            build("sheets", "v4", credentials=creds))


# --------------------------------------------------------------------------- #
# LOCALIZAR / CRIAR
# --------------------------------------------------------------------------- #

def localizar(sa_json: str, pasta_raiz: str,
              titulo: str = TITULO_PADRAO) -> dict | None:
    """Procura a planilha pelo titulo dentro da pasta-raiz. None se nao existir."""
    drive, _ = _servicos(sa_json)
    q = (f"name = '{titulo}' and "
         f"mimeType = 'application/vnd.google-apps.spreadsheet' and "
         f"'{pasta_raiz}' in parents and trashed = false")
    achados = drive.files().list(
        q=q, fields="files(id, name, webViewLink)", supportsAllDrives=True,
        includeItemsFromAllDrives=True).execute().get("files", [])
    if not achados:
        return None
    f = achados[0]
    return {"id": f["id"], "titulo": f["name"], "link": f.get("webViewLink", "")}


def criar(sa_json: str, pasta_raiz: str, titulo: str = TITULO_PADRAO) -> dict:
    """Cria a planilha na pasta-raiz, com todas as abas, cabecalhos e formatacao."""
    drive, sheets = _servicos(sa_json)

    corpo = {
        "properties": {"title": titulo, "locale": "pt_BR",
                       "timeZone": "America/Fortaleza"},
        "sheets": [{"properties": {"title": aba, "gridProperties":
                                   {"frozenRowCount": 1}}}
                   for aba in ABAS],
    }
    planilha = sheets.spreadsheets().create(
        body=corpo, fields="spreadsheetId,spreadsheetUrl,sheets.properties").execute()
    sid = planilha["spreadsheetId"]

    # cabecalhos
    dados = [{"range": f"{aba}!A1", "values": [cols]} for aba, cols in ABAS.items()]
    sheets.spreadsheets().values().batchUpdate(
        spreadsheetId=sid,
        body={"valueInputOption": "USER_ENTERED", "data": dados}).execute()

    # formatacao do cabecalho + auto-resize
    pedidos = []
    for folha in planilha.get("sheets", []):
        gid = folha["properties"]["sheetId"]
        n = len(ABAS.get(folha["properties"]["title"], []))
        pedidos.append({"repeatCell": {
            "range": {"sheetId": gid, "startRowIndex": 0, "endRowIndex": 1},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.16, "green": 0.20, "blue": 0.29},
                "textFormat": {"bold": True, "fontSize": 10,
                               "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "verticalAlignment": "MIDDLE"}},
            "fields": "userEnteredFormat(backgroundColor,textFormat,verticalAlignment)"}})
        if n:
            pedidos.append({"autoResizeDimensions": {"dimensions": {
                "sheetId": gid, "dimension": "COLUMNS",
                "startIndex": 0, "endIndex": n}}})
    if pedidos:
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=sid, body={"requests": pedidos}).execute()

    # move para a pasta-raiz
    atual = drive.files().get(fileId=sid, fields="parents",
                              supportsAllDrives=True).execute()
    drive.files().update(
        fileId=sid, addParents=pasta_raiz,
        removeParents=",".join(atual.get("parents", [])),
        fields="id, parents", supportsAllDrives=True).execute()

    return {"id": sid, "titulo": titulo,
            "link": planilha.get("spreadsheetUrl",
                                 f"https://docs.google.com/spreadsheets/d/{sid}")}


def garantir(sa_json: str, pasta_raiz: str,
             titulo: str = TITULO_PADRAO) -> tuple[dict, bool]:
    """Devolve (info, foi_criada). Nao duplica planilha existente."""
    existente = localizar(sa_json, pasta_raiz, titulo)
    if existente:
        return existente, False
    return criar(sa_json, pasta_raiz, titulo), True


def garantir_abas(sa_json: str, planilha_id: str) -> list[str]:
    """Cria abas ausentes numa planilha que ja existe. Retorna as criadas."""
    _, sheets = _servicos(sa_json)
    meta = sheets.spreadsheets().get(spreadsheetId=planilha_id,
                                     fields="sheets.properties.title").execute()
    presentes = {s["properties"]["title"] for s in meta.get("sheets", [])}
    faltantes = [a for a in ABAS if a not in presentes]
    if not faltantes:
        return []
    sheets.spreadsheets().batchUpdate(
        spreadsheetId=planilha_id,
        body={"requests": [{"addSheet": {"properties": {
            "title": a, "gridProperties": {"frozenRowCount": 1}}}}
            for a in faltantes]}).execute()
    sheets.spreadsheets().values().batchUpdate(
        spreadsheetId=planilha_id,
        body={"valueInputOption": "USER_ENTERED",
              "data": [{"range": f"{a}!A1", "values": [ABAS[a]]}
                       for a in faltantes]}).execute()
    return faltantes


# --------------------------------------------------------------------------- #
# ESCRITA
# --------------------------------------------------------------------------- #

def _append(sa_json: str, planilha_id: str, aba: str, linhas: list[list]) -> int:
    if not linhas:
        return 0
    _, sheets = _servicos(sa_json)
    sheets.spreadsheets().values().append(
        spreadsheetId=planilha_id, range=f"{aba}!A:Z",
        valueInputOption="USER_ENTERED", insertDataOption="INSERT_ROWS",
        body={"values": linhas}).execute()
    return len(linhas)


def registrar_documento(sa_json: str, planilha_id: str, doc: dict,
                        completude: float = 0.0) -> None:
    """Alimenta a aba Documentos com os dados reais da peca."""
    import json as _json

    def lista(v):
        if isinstance(v, str):
            try:
                v = _json.loads(v)
            except _json.JSONDecodeError:
                return v
        return ", ".join(map(str, v)) if isinstance(v, list) else (v or "")

    linha = [
        dt.datetime.now(TZ).isoformat(timespec="seconds"),
        doc.get("id", ""), doc.get("tipologia", ""), doc.get("materia", ""),
        lista(doc.get("modelos")), doc.get("servidor", ""),
        doc.get("matricula", ""), doc.get("assunto", ""), doc.get("processo", ""),
        doc.get("status", ""), doc.get("versao_atual", 1), completude,
        lista(doc.get("campos_faltantes")), doc.get("arquivo_nome", ""),
        doc.get("drive_link", ""), lista(doc.get("provedores")),
        doc.get("hash", ""),
    ]
    _append(sa_json, planilha_id, "Documentos", [linha])


def registrar_lacunas(sa_json: str, planilha_id: str, doc_id, servidor: str,
                      matricula: str, lacunas: list[str],
                      pistas: dict[str, str] | None = None) -> int:
    if not lacunas:
        return 0
    agora = dt.datetime.now(TZ).isoformat(timespec="seconds")
    pistas = pistas or {}
    linhas = [[agora, doc_id, servidor, matricula, c,
               pistas.get(c, ""), "", ""] for c in lacunas]
    return _append(sa_json, planilha_id, "Lacunas", linhas)


def sincronizar_servidores(sa_json: str, planilha_id: str,
                           servidores: list[dict]) -> int:
    """Reescreve a aba Servidores a partir do SQLite."""
    _, sheets = _servicos(sa_json)
    sheets.spreadsheets().values().clear(
        spreadsheetId=planilha_id, range="Servidores!A2:Z").execute()
    linhas = [[s.get("matricula", ""), s.get("nome", ""), s.get("cargo", ""),
               s.get("unidade", ""), s.get("qtd_documentos", 0),
               s.get("ultima_movimentacao", ""), s.get("atualizado_em", ""),
               s.get("observacoes", "")] for s in servidores]
    if linhas:
        sheets.spreadsheets().values().update(
            spreadsheetId=planilha_id, range="Servidores!A2",
            valueInputOption="USER_ENTERED", body={"values": linhas}).execute()
    return len(linhas)


def ler_aba(sa_json: str, planilha_id: str, aba: str = "Documentos",
            limite: int = 500) -> list[dict]:
    """Le a aba de volta — a planilha funciona como banco consultavel."""
    _, sheets = _servicos(sa_json)
    valores = sheets.spreadsheets().values().get(
        spreadsheetId=planilha_id, range=f"{aba}!A1:Z{limite + 1}"
    ).execute().get("values", [])
    if not valores:
        return []
    cabecalho = valores[0]
    return [dict(zip(cabecalho, linha + [""] * (len(cabecalho) - len(linha))))
            for linha in valores[1:]]
