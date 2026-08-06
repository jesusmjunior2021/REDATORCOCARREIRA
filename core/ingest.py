#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/ingest.py — Ampliacao da base de conhecimento.

Rota: o operador sobe um PDF (resolucao, portaria, edital, modelo de peca).
O LlamaParse converte para Markdown; um modelo de inferencia gera o frontmatter
canonico (id, tipologia, materia, situacao, campos_obrigatorios, palavras-chave);
o resultado e gravado como .md em kb/ E internalizado no SQLite.

Nada e inventado: o frontmatter descreve o que o documento e, nao inventa conteudo.
O corpo do .md e o Markdown fiel devolvido pelo LlamaParse.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from . import llm, parsing
from .db import Banco
from .keys import KeyPool

BASES = ("01_BASE_RH_AUXILIO_BOLSA", "02_BASE_GERAL_DOCUMENTOS")

PREFIXOS = {
    "INFORMACAO": "MOD-INF", "DESPACHO": "MOD-DES", "OFICIO": "MOD-OFI",
    "MEMORANDO": "MOD-MEM", "MANIFESTACAO": "MOD-MAN", "REQUERIMENTO": "MOD-REQ",
}

SYS_FRONTMATTER = (
    "Voce cataloga documentos administrativos do TJMA para uma base de conhecimento. "
    "Leia o documento e descreva-o. Responda EXCLUSIVAMENTE com JSON valido. "
    "Nao invente informacao que nao esteja no documento; use null quando nao souber."
)

SCHEMA_FM = """{
  "natureza": "modelo|norma|logica|referencia",
  "tipologia": "INFORMACAO|DESPACHO|OFICIO|MEMORANDO|MANIFESTACAO|REQUERIMENTO|null",
  "materia": "assunto administrativo em poucas palavras",
  "situacao": "situacao processual concreta que o documento cobre, ou vazio",
  "base_sugerida": "01_BASE_RH_AUXILIO_BOLSA|02_BASE_GERAL_DOCUMENTOS",
  "palavras_chave": ["ate 8 termos de busca"],
  "campos_obrigatorios": ["CAMPOS em CAIXA_ALTA que precisam ser preenchidos, se for modelo"],
  "normas_citadas": ["resolucoes, portarias e artigos citados no texto"],
  "resumo": "uma frase sobre o que o documento e"
}"""


@dataclass
class ResultadoIngestao:
    ok: bool
    identificador: str = ""
    caminho: str = ""
    base: str = ""
    natureza: str = ""
    origem_extracao: str = ""
    paginas: int = 0
    frontmatter: dict | None = None
    markdown: str = ""
    erro: str = ""


# --------------------------------------------------------------------------- #
# AUXILIARES
# --------------------------------------------------------------------------- #

def _slug(texto: str, limite: int = 48) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^\w\s-]", "", texto).strip().lower()
    texto = re.sub(r"[\s_]+", "_", texto)
    return texto[:limite] or "documento"


def _id_unico(banco: Banco, prefixo: str) -> str:
    existentes = {k["identificador"] for k in banco.listar_kb(apenas_ativos=False)}
    n = 1
    while f"{prefixo}-{n:02d}" in existentes:
        n += 1
    return f"{prefixo}-{n:02d}"


def _monta_md(identificador: str, fm: dict, corpo: str,
              arquivo_fonte: str, origem: str) -> str:
    linhas = ["---", f"id: {identificador}"]
    if fm.get("tipologia") and fm["tipologia"] not in ("null", None):
        linhas.append(f"tipologia: {fm['tipologia']}")
    if fm.get("natureza") and fm["natureza"] != "modelo":
        mapa = {"norma": "norma", "logica": "logica_de_classificacao",
                "referencia": "referencia"}
        linhas.append(f"tipo: {mapa.get(fm['natureza'], fm['natureza'])}")
    if fm.get("materia"):
        linhas.append(f"materia: {fm['materia']}")
    if fm.get("situacao"):
        linhas.append(f"situacao: {fm['situacao']}")
    if fm.get("palavras_chave"):
        linhas.append(f"palavras_chave: [{', '.join(fm['palavras_chave'][:8])}]")
    if fm.get("campos_obrigatorios"):
        linhas.append("campos_obrigatorios: ["
                      + ", ".join(fm["campos_obrigatorios"]) + "]")
    if fm.get("normas_citadas"):
        linhas.append(f"normas_citadas: [{', '.join(fm['normas_citadas'][:10])}]")
    linhas += [f"origem: {origem}", f"arquivo_fonte: {arquivo_fonte}", "---", ""]
    if fm.get("resumo"):
        linhas += [f"> {fm['resumo']}", ""]
    linhas.append(corpo)
    return "\n".join(linhas)


# --------------------------------------------------------------------------- #
# INGESTAO
# --------------------------------------------------------------------------- #

def ingerir(pool: KeyPool, banco: Banco, nome: str, conteudo: bytes,
            kb_dir: Path, base_forcada: str = "", ordem: list[str] | None = None,
            instrucao_parse: str = parsing.INSTRUCAO_PADRAO,
            gravar_em_disco: bool = True,
            progresso=None) -> ResultadoIngestao:
    """PDF/DOCX/ODT/MD -> Markdown -> frontmatter -> kb/*.md + SQLite."""

    # .md ja pronto entra direto
    if nome.lower().endswith(".md"):
        markdown = conteudo.decode("utf-8", errors="replace")
        origem_extracao = "upload_md"
        paginas = 0
        if progresso:
            progresso(40, "Markdown recebido diretamente.")
    else:
        if progresso:
            progresso(15, f"Convertendo {nome} com LlamaParse...")
        pr = parsing.parse_documento(pool, nome, conteudo, instrucao_parse)
        if not pr.ok:
            return ResultadoIngestao(False, erro=pr.erro or "extracao vazia",
                                     origem_extracao=pr.origem)
        markdown, origem_extracao, paginas = pr.markdown, pr.origem, pr.paginas

    if progresso:
        progresso(55, "Catalogando o documento...")

    fm: dict = {}
    try:
        user = (f"NOME DO ARQUIVO: {nome}\n\nDOCUMENTO (Markdown):\n"
                f"{markdown[:30000]}\n\nSCHEMA:\n{SCHEMA_FM}\n\nResponda apenas o JSON.")
        r = llm.completar(pool, SYS_FRONTMATTER, user, ordem,
                          max_tokens=1500, json_mode=True)
        fm = llm.json_da_resposta(r.texto)
    except Exception as exc:                                  # noqa: BLE001
        fm = {"natureza": "referencia", "tipologia": None,
              "materia": Path(nome).stem, "situacao": "",
              "base_sugerida": BASES[1], "palavras_chave": [],
              "campos_obrigatorios": [], "normas_citadas": [],
              "resumo": f"catalogacao automatica indisponivel ({exc})"}

    natureza = fm.get("natureza") or "referencia"
    tipologia = (fm.get("tipologia") or "").upper()
    base = base_forcada or fm.get("base_sugerida") or BASES[1]
    if base not in BASES:
        base = BASES[1]

    if natureza == "modelo" and tipologia in PREFIXOS:
        identificador = _id_unico(banco, PREFIXOS[tipologia])
    elif natureza == "norma":
        identificador = _id_unico(banco, "NORM")
    elif natureza == "logica":
        identificador = _id_unico(banco, "LOG")
    else:
        identificador = _id_unico(banco, "REF")

    caminho_rel = f"{base}/{identificador}_{_slug(fm.get('materia') or Path(nome).stem)}.md"
    conteudo_md = _monta_md(identificador, fm, markdown, nome, origem_extracao)

    if progresso:
        progresso(85, "Gravando na base de conhecimento...")

    banco.upsert_kb(identificador, caminho_rel, base, conteudo_md, fm,
                    origem=origem_extracao, arquivo_fonte=nome)

    if gravar_em_disco:
        destino = Path(kb_dir) / caminho_rel
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(conteudo_md, encoding="utf-8")

    banco.log("ingestao", f"{nome} -> {caminho_rel} ({origem_extracao})",
              provedor=origem_extracao)

    if progresso:
        progresso(100, "Concluido.")

    return ResultadoIngestao(True, identificador, caminho_rel, base, natureza,
                             origem_extracao, paginas, fm, conteudo_md)


def ingerir_lote(pool: KeyPool, banco: Banco, arquivos: list[tuple[str, bytes]],
                 kb_dir: Path, base_forcada: str = "",
                 ordem: list[str] | None = None,
                 progresso=None) -> list[ResultadoIngestao]:
    saida = []
    total = max(len(arquivos), 1)
    for i, (nome, blob) in enumerate(arquivos, 1):
        def prog(p, m, i=i):
            if progresso:
                progresso(int((i - 1) / total * 100 + p / total),
                          f"[{i}/{total}] {m}")
        saida.append(ingerir(pool, banco, nome, blob, kb_dir, base_forcada,
                             ordem, progresso=prog))
    return saida
