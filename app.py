#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
app.py — REDATOR COCARREIRA/CAEDNC (TJMA)

Interface de chat. Fluxo sem estrutura rigida: o operador descreve o caso em
linguagem natural e anexa o que tiver. O pipeline faz o resto.

    streamlit run app.py
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import streamlit as st

from core import kb as kbmod
from core import exporters, parsing, pipeline
from core.keys import (KeyPool, PROVIDERS, ORDEM_PADRAO_INFERENCIA, TZ)

APP_DIR = Path(__file__).resolve().parent
KB_DIR = APP_DIR / "kb"
SAIDA_DIR = APP_DIR / "saida"
PERFIS_DIR = APP_DIR / "perfis"
ARQ_CHAVES = APP_DIR / "api_keys.json"
ARQ_HIST = APP_DIR / "historico_documentos.json"
PROMPT_MESTRE = APP_DIR / "GEM_REDATOR_PROMPT.md"


# --------------------------------------------------------------------------- #
# ESTADO
# --------------------------------------------------------------------------- #

@st.cache_resource
def _pool() -> KeyPool:
    return KeyPool(ARQ_CHAVES)


@st.cache_data(show_spinner=False)
def _docs_cache(carimbo: float) -> list:
    return kbmod.carregar(KB_DIR)


def carregar_docs() -> list:
    carimbo = max((p.stat().st_mtime for p in KB_DIR.rglob("*.md")), default=0.0)
    return _docs_cache(carimbo)


def init_estado() -> None:
    st.session_state.setdefault("mensagens", [])
    st.session_state.setdefault("resultado", None)
    st.session_state.setdefault("anexos_processados", [])


# --------------------------------------------------------------------------- #
# BARRA LATERAL
# --------------------------------------------------------------------------- #

def barra_lateral(pool: KeyPool, docs: list) -> dict:
    cfg: dict = {}
    with st.sidebar:
        st.markdown("### Pipeline")
        st.caption("LlamaParse → Groq/Cerebras → montagem Python sobre os .md")

        parse_ok = pool.disponiveis("llamaparse")
        infer_ok = sum(pool.disponiveis(p) for p in ORDEM_PADRAO_INFERENCIA)
        c1, c2 = st.columns(2)
        c1.metric("Parsing", parse_ok)
        c2.metric("Inferencia", infer_ok)
        if not infer_ok:
            st.error("Sem chave de inferencia. Cadastre abaixo.")
        if not parse_ok:
            st.warning("Sem LlamaParse: PDF escaneado nao sera lido (fallback local "
                       "so extrai PDF com camada de texto).")

        with st.expander("Chaves de API", expanded=not infer_ok):
            prov = st.selectbox("Provedor", list(PROVIDERS.keys()),
                                format_func=lambda p: f"{p} ({PROVIDERS[p]['papel']})")
            chave = st.text_input("Chave", type="password", key="in_chave")
            rotulo = st.text_input("Rotulo", value="chave-1", key="in_rotulo")
            validar = st.checkbox("Validar antes de adicionar", value=True)
            if st.button("Adicionar", use_container_width=True):
                if not chave.strip():
                    st.error("Informe a chave.")
                else:
                    ok, msg = pool.add(prov, chave.strip(), rotulo, validar)
                    (st.success if ok else st.error)(f"{prov}: {msg}")
                    st.rerun()

            resumo = pool.resumo()
            if resumo:
                st.dataframe(resumo, use_container_width=True, hide_index=True)
                alvo = st.selectbox(
                    "Remover chave",
                    ["(nenhuma)"] + [f"{l['provedor']} · {l['rotulo']}" for l in resumo])
                if alvo != "(nenhuma)" and st.button("Remover", use_container_width=True):
                    p, r = alvo.split(" · ", 1)
                    for k in pool.data.get(p, []):
                        if k.get("label") == r:
                            pool.remove(p, k["key"])
                            break
                    st.rerun()

            st.download_button("Exportar JSON", pool.export_json(),
                               file_name="api_keys.json", mime="application/json",
                               use_container_width=True)
            subida = st.file_uploader("Importar JSON", type=["json"], key="imp_chaves")
            if subida is not None and st.button("Aplicar importacao",
                                                use_container_width=True):
                n = pool.import_json(subida.read())
                st.success(f"{n} chave(s) importada(s).")
                st.rerun()

        with st.expander("Rodizio e modelos"):
            cfg["ordem"] = st.multiselect(
                "Prioridade dos provedores de inferencia",
                ORDEM_PADRAO_INFERENCIA, default=ORDEM_PADRAO_INFERENCIA)
            cfg["modelo"] = st.text_input("Forcar modelo (opcional)", value="")
            cfg["usar_llamaparse"] = st.checkbox("Usar LlamaParse quando disponivel",
                                                 value=True)

        with st.expander("Instrucao de extracao (LlamaParse)"):
            cfg["instrucao_parse"] = st.text_area(
                "Instrucao em linguagem natural", value=parsing.INSTRUCAO_PADRAO,
                height=160)

        with st.expander("Google Service Account"):
            cfg["sa"] = st.text_input("Caminho do service_account.json",
                                      value=str(APP_DIR / "service_account.json"))
            cfg["pasta_raiz"] = st.text_input("ID da pasta-raiz no Drive")
            cfg["planilha"] = st.text_input("ID da planilha de registro")

        with st.expander("Base de conhecimento"):
            st.caption(f"{len(docs)} arquivos .md | "
                       f"{len(kbmod.catalogo(docs))} modelos redigiveis")
            if st.button("Recarregar base", use_container_width=True):
                st.cache_data.clear()
                st.rerun()
    return cfg


# --------------------------------------------------------------------------- #
# ABA: REDIGIR
# --------------------------------------------------------------------------- #

def aba_redigir(pool: KeyPool, docs: list, cfg: dict) -> None:
    catalogo = kbmod.catalogo(docs)

    for m in st.session_state["mensagens"]:
        with st.chat_message(m["papel"]):
            st.markdown(m["texto"])

    with st.expander("Anexos e ajustes", expanded=not st.session_state["mensagens"]):
        col1, col2 = st.columns([3, 2])
        with col1:
            anexos = st.file_uploader(
                "Documentos do caso (PDF, DOCX, ODT, TXT)",
                type=["pdf", "docx", "odt", "txt", "md"],
                accept_multiple_files=True, key="anexos")
        with col2:
            modo = st.radio("Tipologia",
                            ["Detectar automaticamente", "Eu indico o modelo"],
                            horizontal=False)
            forcados: list[str] = []
            if modo == "Eu indico o modelo":
                escolhas = st.multiselect(
                    "Modelo(s)", [d.rotulo for d in catalogo])
                forcados = [r.split(" — ")[0] for r in escolhas]
            extra = st.text_input("Instrucao adicional de redacao (opcional)")

    relato = st.chat_input("Descreva o caso: quem pede, o que pede, de onde para onde, "
                           "o que ja consta nos autos...")

    if relato:
        st.session_state["mensagens"].append({"papel": "user", "texto": relato})
        with st.chat_message("user"):
            st.markdown(relato)

        arquivos = [(a.name, a.getvalue()) for a in (anexos or [])]

        with st.chat_message("assistant"):
            barra = st.progress(0, text="Iniciando...")
            def prog(pct: int, msg: str) -> None:
                barra.progress(min(pct, 100), text=msg)

            try:
                res = pipeline.executar(
                    pool, docs, relato, arquivos,
                    modelos_forcados=forcados or None,
                    ordem_inferencia=cfg.get("ordem") or ORDEM_PADRAO_INFERENCIA,
                    prompt_mestre=PROMPT_MESTRE,
                    instrucao_parse=cfg.get("instrucao_parse",
                                            parsing.INSTRUCAO_PADRAO),
                    instrucoes_extra=(f"7. {extra}" if extra else ""),
                    progresso=prog)
            except Exception as exc:
                barra.empty()
                st.error(f"Falha no pipeline: {exc}")
                st.session_state["mensagens"].append(
                    {"papel": "assistant", "texto": f"Falha: {exc}"})
                return

            barra.empty()
            st.session_state["resultado"] = res
            st.markdown(res.documento)
            st.session_state["mensagens"].append(
                {"papel": "assistant", "texto": res.documento})

    res = st.session_state.get("resultado")
    if not res:
        return

    st.divider()
    t1, t2, t3 = st.tabs(["Trilha do pipeline", "Entidades extraidas", "Anexos lidos"])
    with t1:
        for passo in res.trilha:
            st.text(passo)
        st.json(res.classificacao)
        if res.campos_faltantes:
            st.warning("Campos faltantes: " + ", ".join(res.campos_faltantes))
        else:
            st.success("Nenhum campo faltante.")
    with t2:
        st.json(res.entidades)
    with t3:
        for e in res.extracoes:
            st.markdown(f"**{e.nome}** — extracao: `{e.origem}`"
                        + (f" — {e.paginas} pag." if e.paginas else "")
                        + (f" — {e.erro}" if e.erro else ""))
            st.text_area(e.nome, e.markdown[:6000], height=180, key=f"ex_{e.nome}")

    st.divider()
    st.markdown("#### Identificacao para arquivamento")
    sug = res.entidades.get("servidores") or [{}]
    p = res.entidades.get("processo") or {}
    c1, c2, c3, c4 = st.columns(4)
    nome = c1.text_input("Servidor", value=(sug[0].get("nome") or ""))
    matricula = c2.text_input("Matricula", value=(sug[0].get("matricula") or ""))
    assunto = c3.text_input("Assunto", value=(p.get("assunto") or ""))
    processo = c4.text_input("Processo", value=(p.get("numero") or ""))

    texto_final = st.text_area("Documento (editavel antes de salvar)",
                               res.documento, height=380)

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Salvar .docx", use_container_width=True):
            arq = exporters.nome_arquivo(matricula, nome, assunto, res.tipologia)
            destino = exporters.salvar_docx(texto_final, SAIDA_DIR / f"{arq}.docx")
            st.success(f"Salvo: {destino.name}")
            st.download_button("Baixar", destino.read_bytes(), file_name=destino.name,
                               use_container_width=True)
    with b2:
        if st.button("Enviar ao Google Docs", type="primary", use_container_width=True):
            if not cfg.get("pasta_raiz"):
                st.error("Informe o ID da pasta-raiz do Drive na barra lateral.")
            else:
                try:
                    info = exporters.enviar_google_docs(
                        texto_final, cfg["sa"], cfg["pasta_raiz"],
                        matricula, nome, assunto, res.tipologia)
                    st.success(f"Criado em {info['pasta']}")
                    st.markdown(f"[Abrir documento]({info['link']})")

                    entrada = {
                        "data_hora": dt.datetime.now(TZ).isoformat(),
                        "tipologia": res.tipologia,
                        "modelos": res.modelos_usados,
                        "servidor": nome, "matricula": matricula,
                        "assunto": assunto, "processo": processo,
                        "arquivo": info["arquivo"], "link": info["link"],
                        "campos_faltantes": res.campos_faltantes,
                        "provedores": res.provedores, "hash": res.hash,
                    }
                    hist = exporters.registrar_historico(entrada, ARQ_HIST)
                    if cfg.get("planilha"):
                        exporters.registrar_planilha(
                            [entrada["data_hora"], res.tipologia,
                             ", ".join(res.modelos_usados), nome, matricula,
                             assunto, processo, info["arquivo"], info["link"],
                             ", ".join(res.campos_faltantes),
                             ", ".join(res.provedores), res.hash],
                            cfg["sa"], cfg["planilha"])
                    perfil = exporters.consolidar_perfil(hist, matricula, PERFIS_DIR)
                    if perfil:
                        st.info(f"Perfil consolidado: {perfil.name}")
                except Exception as exc:
                    st.error(f"Falha no envio: {exc}")


# --------------------------------------------------------------------------- #
# ABAS AUXILIARES
# --------------------------------------------------------------------------- #

def aba_catalogo(docs: list) -> None:
    catalogo = kbmod.catalogo(docs)
    st.subheader(f"{len(catalogo)} modelos que a aplicacao sabe redigir")
    busca = st.text_input("Buscar por intencao (fuzzy)")
    if busca:
        ranking = kbmod.pre_selecionar(docs, busca, limite=10, minimo=0.0)
        st.dataframe([{"score": s, "ID": d.id, "Tipologia": d.tipologia,
                       "Materia": d.materia, "Situacao": d.situacao}
                      for d, s in ranking], use_container_width=True, hide_index=True)
    else:
        st.dataframe([{"ID": d.id, "Tipologia": d.tipologia, "Materia": d.materia,
                       "Situacao": d.situacao, "Par": d.par, "Base": d.base,
                       "Campos": len(d.campos)} for d in catalogo],
                     use_container_width=True, hide_index=True)

    ident = st.selectbox("Inspecionar modelo",
                         ["(nenhum)"] + [d.id for d in catalogo])
    if ident != "(nenhum)":
        d = kbmod.por_id(docs, ident)
        st.code(d.texto, language="markdown")


def aba_historico() -> None:
    if not ARQ_HIST.exists():
        st.info("Nenhum documento gerado ainda.")
        return
    hist = json.loads(ARQ_HIST.read_text(encoding="utf-8"))
    st.dataframe(hist, use_container_width=True, hide_index=True)
    st.download_button("Exportar historico (JSON)",
                       json.dumps(hist, ensure_ascii=False, indent=2),
                       file_name="historico_documentos.json", mime="application/json")


# --------------------------------------------------------------------------- #
# MAIN
# --------------------------------------------------------------------------- #

def main() -> None:
    st.set_page_config(page_title="Redator COCARREIRA", layout="wide",
                       initial_sidebar_state="expanded")
    init_estado()
    pool = _pool()
    docs = carregar_docs()
    cfg = barra_lateral(pool, docs)

    st.title("Redator de Documentos Oficiais — COCARREIRA/CAEDNC")

    t_redigir, t_catalogo, t_hist = st.tabs(
        ["Redigir", "Catalogo de modelos", "Historico"])
    with t_redigir:
        aba_redigir(pool, docs, cfg)
    with t_catalogo:
        aba_catalogo(docs)
    with t_hist:
        aba_historico()


if __name__ == "__main__":
    main()
