#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cli.py — execucao headless do pipeline, para lote e automacao.

Exemplos:
  python cli.py --relato "servidor pediu relotacao, chefia concordou" \
                --anexo dossie.pdf --anexo certidao.pdf \
                --nome "FULANO" --matricula 102350 --assunto "Relotacao" \
                --docx --drive

  python cli.py --catalogo
  python cli.py --chave groq:gsk_xxx --chave llamaparse:llx_xxx
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from core import kb as kbmod
from core import exporters, parsing, pipeline
from core.keys import KeyPool, ORDEM_PADRAO_INFERENCIA, TZ

APP_DIR = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser(description="Redator COCARREIRA — CLI")
    ap.add_argument("--relato", default="", help="descricao do caso em linguagem natural")
    ap.add_argument("--anexo", action="append", default=[], help="caminho de anexo (repetivel)")
    ap.add_argument("--modelo", action="append", default=[], help="forcar ID de modelo")
    ap.add_argument("--nome", default="")
    ap.add_argument("--matricula", default="")
    ap.add_argument("--assunto", default="")
    ap.add_argument("--processo", default="")
    ap.add_argument("--ordem", default=",".join(ORDEM_PADRAO_INFERENCIA))
    ap.add_argument("--docx", action="store_true", help="salvar .docx em saida/")
    ap.add_argument("--drive", action="store_true", help="enviar ao Google Docs")
    ap.add_argument("--sa", default=str(APP_DIR / "service_account.json"))
    ap.add_argument("--pasta-raiz", default="")
    ap.add_argument("--planilha", default="")
    ap.add_argument("--catalogo", action="store_true", help="listar modelos e sair")
    ap.add_argument("--chave", action="append", default=[],
                    help="cadastrar chave no formato provedor:valor")
    ap.add_argument("--json", action="store_true", help="saida em JSON")
    args = ap.parse_args()

    pool = KeyPool(APP_DIR / "api_keys.json")
    docs = kbmod.carregar(APP_DIR / "kb")

    for par in args.chave:
        if ":" not in par:
            print(f"formato invalido: {par}", file=sys.stderr)
            continue
        prov, val = par.split(":", 1)
        ok, msg = pool.add(prov.strip(), val.strip(), "cli")
        print(f"{prov}: {msg}")
    if args.chave and not args.relato:
        return 0

    if args.catalogo:
        for d in kbmod.catalogo(docs):
            print(f"{d.id:<12} {d.tipologia:<14} {d.materia} | {d.situacao}")
        return 0

    if not args.relato and not args.anexo:
        ap.error("informe --relato e/ou --anexo")

    anexos = []
    for caminho in args.anexo:
        p = Path(caminho)
        if not p.exists():
            print(f"anexo inexistente: {p}", file=sys.stderr)
            return 2
        anexos.append((p.name, p.read_bytes()))

    def prog(pct, msg):
        print(f"[{pct:>3}%] {msg}", file=sys.stderr)

    res = pipeline.executar(
        pool, docs, args.relato, anexos,
        modelos_forcados=args.modelo or None,
        ordem_inferencia=[p.strip() for p in args.ordem.split(",") if p.strip()],
        prompt_mestre=APP_DIR / "GEM_REDATOR_PROMPT.md",
        instrucao_parse=parsing.INSTRUCAO_PADRAO,
        progresso=prog)

    saida = {
        "documento": res.documento,
        "tipologia": res.tipologia,
        "modelos": res.modelos_usados,
        "campos_faltantes": res.campos_faltantes,
        "trilha": res.trilha,
        "provedores": res.provedores,
        "hash": res.hash,
    }

    if args.docx:
        arq = exporters.nome_arquivo(args.matricula, args.nome, args.assunto, res.tipologia)
        destino = exporters.salvar_docx(res.documento, APP_DIR / "saida" / f"{arq}.docx")
        saida["docx"] = str(destino)

    if args.drive:
        if not args.pasta_raiz:
            print("--drive exige --pasta-raiz", file=sys.stderr)
            return 2
        info = exporters.enviar_google_docs(
            res.documento, args.sa, args.pasta_raiz,
            args.matricula, args.nome, args.assunto, res.tipologia)
        saida.update(info)
        entrada = {
            "data_hora": dt.datetime.now(TZ).isoformat(), "tipologia": res.tipologia,
            "modelos": res.modelos_usados, "servidor": args.nome,
            "matricula": args.matricula, "assunto": args.assunto,
            "processo": args.processo, "arquivo": info["arquivo"],
            "link": info["link"], "campos_faltantes": res.campos_faltantes,
            "provedores": res.provedores, "hash": res.hash,
        }
        hist = exporters.registrar_historico(entrada, APP_DIR / "historico_documentos.json")
        if args.planilha:
            exporters.registrar_planilha(
                [entrada[c] if isinstance(entrada.get(c), str) else
                 ", ".join(entrada.get(c, [])) for c in exporters.CABECALHO_PLANILHA],
                args.sa, args.planilha)
        perfil = exporters.consolidar_perfil(hist, args.matricula, APP_DIR / "perfis")
        if perfil:
            saida["perfil"] = str(perfil)

    if args.json:
        print(json.dumps(saida, ensure_ascii=False, indent=2))
    else:
        print(res.documento)
        if res.campos_faltantes:
            print("\n--- CAMPOS FALTANTES ---", file=sys.stderr)
            for c in res.campos_faltantes:
                print(f"  - {c}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
