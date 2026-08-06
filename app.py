#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
app.py — REDATOR COCARREIRA/CAEDNC (TJMA) — v3.0

  1. REDIGIR    relato + anexos -> botao INICIAR PROCESSAMENTO -> pipeline real
  2. EDITOR     folha A4 com editor WYSIWYG (negrito/italico/sublinhado/alinhamento/
                recuo/listas/tabelas), cabecalho e rodape editaveis, versionamento
  3. GALERIA    tudo que foi salvo no SQLite, com busca, versoes e reabertura
  4. BASE       ingestao de PDF -> LlamaParse -> .md -> banco; ativar/desativar
  5. SISTEMA    chaves, rodizio, Drive, estatisticas, exportacoes

    streamlit run app.py
"""

from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

import os
import sys

import streamlit as st

# --------------------------------------------------------------------------- #
# BOOTSTRAP — garante que o pacote local `core` seja encontrado.
# Em Streamlit Cloud, Docker e execucoes com cwd diferente, o diretorio do script
# nem sempre entra no sys.path. Sem isto, `from core import ...` levanta
# ModuleNotFoundError (que e subclasse de ImportError) e a Cloud censura a
# mensagem, deixando so "ImportError" — sem dizer o que faltou.
# --------------------------------------------------------------------------- #

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


def _diagnostico(exc: BaseException) -> None:
    """Mostra a causa real do erro de import, em vez da mensagem censurada."""
    st.set_page_config(page_title="Redator — falha na inicialização",
                       layout="wide", page_icon="⚠")
    st.error(f"Falha ao carregar os módulos: **{type(exc).__name__}: {exc}**")

    faltando = getattr(exc, "name", None)
    if faltando and faltando != "core":
        st.markdown(f"### Dependência ausente: `{faltando}`")
        st.markdown("Acrescente ao `requirements.txt` e faça o redeploy:")
        st.code(faltando, language="text")
    elif faltando == "core":
        st.markdown("### A pasta `core/` não está junto do `app.py`")
        st.markdown(
            "No repositório, `app.py`, `core/`, `kb/`, `requirements.txt` e "
            "`schema.yml` precisam estar **na raiz** — não dentro de uma subpasta "
            "`REDATOR_COCARREIRA/`. Se você subiu o zip inteiro, mova o conteúdo "
            "da subpasta para a raiz e faça o commit.")

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Ambiente**")
        st.code(f"Python {sys.version.split()[0]}\n"
                f"Diretório do app: {APP_DIR}\n"
                f"Diretório atual:  {os.getcwd()}", language="text")
        st.markdown("**sys.path**")
        st.code("\n".join(sys.path[:8]), language="text")
    with c2:
        st.markdown("**Conteúdo do diretório do app**")
        try:
            itens = sorted(p.name + ("/" if p.is_dir() else "")
                           for p in APP_DIR.iterdir())
            st.code("\n".join(itens) or "(vazio)", language="text")
        except OSError as e:
            st.code(str(e))
        st.markdown("**Conteúdo de core/**")
        core_dir = APP_DIR / "core"
        if core_dir.is_dir():
            st.code("\n".join(sorted(p.name for p in core_dir.iterdir())),
                    language="text")
        else:
            st.code("core/ NÃO EXISTE neste diretório", language="text")

    with st.expander("Traceback completo"):
        import traceback
        st.code("".join(traceback.format_exception(exc)), language="text")
    st.stop()


try:
    from core import editor as ed
    from core import (exporters, gaps, ingest, kb as kbmod, parsing, pipeline,
                      sheets)
    from core.db import Banco, exportar_pacote_github
    from core.keys import KeyPool, PROVIDERS, ORDEM_PADRAO_INFERENCIA, TZ
except Exception as _exc:                                      # noqa: BLE001
    _diagnostico(_exc)

KB_DIR = APP_DIR / "kb"
SAIDA_DIR = APP_DIR / "saida"
ARQ_CHAVES = APP_DIR / "api_keys.json"
ARQ_DB = APP_DIR / "redator.db"
PROMPT_MESTRE = APP_DIR / "GEM_REDATOR_PROMPT.md"

try:
    from streamlit_quill import st_quill
    TEM_QUILL = True
except ImportError:
    TEM_QUILL = False


# --------------------------------------------------------------------------- #
# RECURSOS
# --------------------------------------------------------------------------- #

@st.cache_resource
def _pool() -> KeyPool:
    return KeyPool(ARQ_CHAVES)


@st.cache_resource
def _banco() -> Banco:
    b = Banco(ARQ_DB)
    if b.estatisticas()["kb_total"] == 0:
        b.sincronizar_kb_do_disco(KB_DIR)
    return b


@st.cache_data(show_spinner=False)
def _docs(carimbo: float) -> list:
    return kbmod.carregar(KB_DIR)


def carregar_docs() -> list:
    carimbo = max((p.stat().st_mtime for p in KB_DIR.rglob("*.md")), default=0.0)
    return _docs(carimbo)


def init_estado() -> None:
    padroes = {
        "resultado": None, "doc_id": None, "corpo_html": "",
        "cabecalho": ed.CABECALHO_PADRAO, "rodape": ed.RODAPE_PADRAO,
        "meta": {}, "ultimo_salvo": None, "docx_bytes": None, "docx_nome": "",
        "dossie": None, "lacunas_manuais": {},
    }
    for chave, valor in padroes.items():
        st.session_state.setdefault(chave, valor)


# --------------------------------------------------------------------------- #
# BARRA LATERAL
# --------------------------------------------------------------------------- #

def barra_lateral(pool: KeyPool, banco: Banco, docs: list) -> dict:
    cfg: dict = {}
    with st.sidebar:
        st.markdown("### Pipeline")
        st.caption("LlamaParse → Groq/Cerebras → montagem Python sobre os .md → SQLite")

        parse_ok = pool.disponiveis("llamaparse")
        infer_ok = sum(pool.disponiveis(p) for p in ORDEM_PADRAO_INFERENCIA)
        est = banco.estatisticas()
        c1, c2, c3 = st.columns(3)
        c1.metric("Parsing", parse_ok)
        c2.metric("Inferência", infer_ok)
        c3.metric("Docs", est["documentos"])

        if not infer_ok:
            st.error("Sem chave de inferência — cadastre na aba Sistema.")
        if not parse_ok:
            st.warning("Sem LlamaParse: PDF escaneado não será lido.")
        if not TEM_QUILL:
            st.warning("Instale `streamlit-quill` para o editor completo.")

        with st.expander("Rodízio e extração"):
            cfg["ordem"] = st.multiselect("Prioridade dos provedores",
                                          ORDEM_PADRAO_INFERENCIA,
                                          default=ORDEM_PADRAO_INFERENCIA)
            cfg["instrucao_parse"] = st.text_area(
                "Instrução de extração (LlamaParse)",
                value=parsing.INSTRUCAO_PADRAO, height=130)

        with st.expander("Google Drive / Sheets"):
            cfg["sa"] = st.text_input(
                "service_account.json",
                value=banco.get_config("sa_path",
                                       str(APP_DIR / "service_account.json")))
            cfg["pasta_raiz"] = st.text_input(
                "ID da pasta-raiz", value=banco.get_config("drive_folder", ""))
            cfg["planilha"] = st.text_input(
                "ID da planilha", value=banco.get_config("sheet_id", ""))
            if st.button("Salvar configuração", use_container_width=True):
                banco.set_config("sa_path", cfg["sa"])
                banco.set_config("drive_folder", cfg["pasta_raiz"])
                banco.set_config("sheet_id", cfg["planilha"])
                st.success("Gravado no SQLite.")

            if not cfg["planilha"]:
                st.caption("Nenhuma planilha vinculada.")
                if st.button("➕ Criar planilha no Drive", type="primary",
                             use_container_width=True,
                             disabled=not cfg["pasta_raiz"]):
                    try:
                        info, criada = sheets.garantir(cfg["sa"], cfg["pasta_raiz"])
                        banco.set_config("sheet_id", info["id"])
                        cfg["planilha"] = info["id"]
                        st.success("Planilha criada." if criada
                                   else "Planilha existente vinculada.")
                        st.markdown(f"[Abrir planilha]({info['link']})")
                        banco.log("sheets",
                                  f"{'criada' if criada else 'vinculada'}: {info['id']}")
                    except Exception as exc:
                        st.error(f"Falha: {exc}")
            else:
                if st.button("↻ Conferir abas da planilha",
                             use_container_width=True):
                    try:
                        criadas = sheets.garantir_abas(cfg["sa"], cfg["planilha"])
                        st.success(f"Abas criadas: {', '.join(criadas)}"
                                   if criadas else "Todas as abas presentes.")
                    except Exception as exc:
                        st.error(f"Falha: {exc}")

        st.divider()
        st.caption(f"Base: {est['kb_ativos']} ativos · "
                   f"{len(kbmod.catalogo(docs))} modelos · {est['versoes']} versões")
    return cfg


# --------------------------------------------------------------------------- #
# PAINEL DE LACUNAS E COMPLETUDE
# --------------------------------------------------------------------------- #

def painel_lacunas(dossie, banco: Banco) -> None:
    """Mostra o que foi caçado nos anexos, com completude por documento."""
    st.markdown("#### Completude da extração dirigida")

    cor = "🟢" if dossie.completude >= 80 else ("🟡" if dossie.completude >= 50 else "🔴")
    st.progress(dossie.completude / 100,
                text=f"{cor} {dossie.completude:.0f}% — "
                     f"{len(dossie.preenchidos)}/{len(dossie.alvos)} campos-alvo "
                     f"localizados · {len(dossie.lacunas)} lacuna(s)")

    st.markdown("**Completude por documento**")
    st.dataframe(
        [{"Documento": d.nome, "Extração": d.origem,
          "Págs.": d.paginas or "—",
          "Campos supridos": len(d.supridos),
          "Completude": f"{d.completude(dossie.alvos):.0f}%",
          "Erro": d.erro or ""} for d in dossie.documentos],
        use_container_width=True, hide_index=True)

    t1, t2, t3 = st.tabs(["✓ Localizados", "⚠ Lacunas", "📄 Evidências .md"])

    with t1:
        achados = [dossie.consolidado[c] for c in dossie.alvos
                   if c in dossie.consolidado and dossie.consolidado[c].encontrado]
        if achados:
            st.dataframe(
                [{"Campo": a.campo, "Valor": a.valor, "Fonte": a.fonte,
                  "Pág.": a.pagina or "—", "Confiança": f"{a.confianca:.2f}",
                  "Trecho": (a.trecho or "")[:80]} for a in achados],
                use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum campo localizado nos anexos.")

    with t2:
        if dossie.lacunas:
            st.warning(f"{len(dossie.lacunas)} campo(s) não encontrados nos anexos. "
                       "Sairão como [DADO FALTANTE] e podem ser preenchidos no editor.")
            st.dataframe(
                [{"Campo": c, "O que procurar": gaps.pista(c)}
                 for c in dossie.lacunas],
                use_container_width=True, hide_index=True)
        else:
            st.success("Nenhuma lacuna: todos os campos-alvo foram supridos.")

    with t3:
        st.caption("Formato .md — é isto que o redator consome, e o que você pode "
                   "commitar no GitHub.")
        st.code(dossie.markdown(), language="markdown")
        for d in dossie.documentos:
            with st.expander(f"Evidências de {d.nome}"):
                st.code(d.markdown_evidencias, language="markdown")

        e1, e2 = st.columns(2)
        e1.download_button("⬇ Baixar DOSSIE.md", dossie.markdown(),
                           file_name="DOSSIE.md", mime="text/markdown",
                           use_container_width=True)
        if e2.button("💾 Gravar evidências em saida/evidencias/",
                     use_container_width=True):
            escritos = gaps.salvar_evidencias(dossie, SAIDA_DIR / "evidencias")
            banco.log("evidencias", f"{len(escritos)} arquivo(s) .md gravados")
            st.success(f"{len(escritos)} arquivo(s) .md gravados.")


# --------------------------------------------------------------------------- #
# ABA 1 — REDIGIR
# --------------------------------------------------------------------------- #

def aba_redigir(pool: KeyPool, banco: Banco, docs: list, cfg: dict) -> None:
    catalogo = kbmod.catalogo(docs)
    col_esq, col_dir = st.columns([3, 2])

    with col_esq:
        st.markdown("#### Caso")
        relato = st.text_area(
            "Descreva o caso: quem pede, o que pede, de onde para onde, "
            "o que já consta nos autos",
            height=170, key="relato",
            placeholder="Ex.: o servidor pediu relotação do 2º Juizado para a "
                        "Secretaria do Conselho; a chefia concordou e a certidão "
                        "de PAD veio negativa.")
        anexos = st.file_uploader(
            "Documentos do caso (PDF, DOCX, ODT, TXT)",
            type=["pdf", "docx", "odt", "txt", "md"],
            accept_multiple_files=True, key="anexos_caso")

    with col_dir:
        st.markdown("#### Tipologia")
        modo = st.radio("Seleção", ["Detectar automaticamente", "Eu indico o modelo"],
                        label_visibility="collapsed")
        forcados: list[str] = []
        if modo == "Eu indico o modelo":
            escolhas = st.multiselect("Modelo(s)", [d.rotulo for d in catalogo])
            forcados = [r.split(" — ")[0] for r in escolhas]
        extra = st.text_input("Instrução adicional de redação (opcional)")

    conhecidos: dict[str, str] = {}
    alvos: list[str] = []
    if forcados:
        alvos = gaps.alvos_do_modelo(docs, kbmod.resolver_pares(docs, forcados))
        st.divider()
        st.markdown(f"#### Campos-alvo do modelo · {len(alvos)} campos")
        st.caption("O LlamaParse será **guiado** para caçar exatamente estes campos "
                   "nos anexos. Preencha aqui apenas o que você já sabe — o resto "
                   "é buscado nos documentos.")
        colunas = st.columns(3)
        for i, campo in enumerate(alvos):
            with colunas[i % 3]:
                valor = st.text_input(
                    campo, key=f"alvo_{campo}",
                    help=gaps.pista(campo),
                    placeholder="buscar nos anexos")
                if valor.strip():
                    conhecidos[campo] = valor.strip()
        preenchidos = len(conhecidos)
        st.progress(preenchidos / max(len(alvos), 1),
                    text=f"Informado manualmente: {preenchidos}/{len(alvos)} "
                         f"— {len(alvos) - preenchidos} serão caçados nos anexos")
    else:
        st.divider()
        st.caption("Selecione um modelo acima para habilitar a extração dirigida "
                   "aos campos-alvo.")

    nome_pre = conhecidos.get("NOME", "")
    matricula_pre = conhecidos.get("MATRICULA", "")

    st.divider()
    pronto = bool(sum(pool.disponiveis(p) for p in ORDEM_PADRAO_INFERENCIA))
    tem_entrada = bool(relato.strip() or anexos)

    b1, b2, b3 = st.columns([2, 1, 1])
    iniciar = b1.button("▶  INICIAR PROCESSAMENTO", type="primary",
                        use_container_width=True,
                        disabled=not (pronto and tem_entrada))
    if b2.button("Limpar", use_container_width=True):
        st.session_state["resultado"] = None
        st.session_state["doc_id"] = None
        st.session_state["corpo_html"] = ""
        st.rerun()
    b3.caption(f"{len(anexos or [])} anexo(s)")

    if not pronto:
        st.info("Cadastre ao menos uma chave de inferência na aba Sistema.")
    elif not tem_entrada:
        st.caption("Descreva o caso ou anexe um documento para habilitar o botão.")

    if not iniciar:
        return

    arquivos = [(a.name, a.getvalue()) for a in (anexos or [])]
    barra = st.progress(0, text="Iniciando...")
    painel = st.empty()
    inicio = time.time()

    def prog(pct: int, msg: str) -> None:
        barra.progress(min(pct, 100), text=msg)
        painel.caption(f"⏱ {time.time() - inicio:0.1f}s — {msg}")

    try:
        res = pipeline.executar(
            pool, docs, relato, arquivos,
            modelos_forcados=forcados or None,
            ordem_inferencia=cfg.get("ordem") or ORDEM_PADRAO_INFERENCIA,
            prompt_mestre=PROMPT_MESTRE,
            instrucao_parse=cfg.get("instrucao_parse", parsing.INSTRUCAO_PADRAO),
            instrucoes_extra=(f"7. {extra}" if extra else ""),
            conhecidos=conhecidos or None,
            progresso=prog)
    except Exception as exc:
        barra.empty()
        painel.empty()
        st.error(f"Falha no pipeline: {exc}")
        banco.log("pipeline", str(exc), nivel="erro")
        return

    barra.empty()
    painel.empty()
    decorrido = time.time() - inicio

    ents = res.entidades.get("servidores") or [{}]
    proc = res.entidades.get("processo") or {}
    st.session_state["resultado"] = res
    st.session_state["corpo_html"] = ed.texto_para_html(res.documento)
    st.session_state["doc_id"] = None
    st.session_state["dossie"] = res.dossie
    st.session_state["meta"] = {
        "servidor": nome_pre or (ents[0].get("nome") or ""),
        "matricula": matricula_pre or (ents[0].get("matricula") or ""),
        "assunto": proc.get("assunto") or "",
        "processo": proc.get("numero") or "",
        "cargo": ents[0].get("cargo") or "",
        "unidade": ents[0].get("unidade_origem") or "",
        "status": "rascunho",
    }
    banco.log("pipeline", f"{res.tipologia} | modelos={res.modelos_usados}",
              provedor=", ".join(res.provedores), duracao=decorrido)

    st.success(f"Documento redigido em {decorrido:0.1f}s — {res.tipologia} · "
               f"modelos {', '.join(res.modelos_usados)}")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Tipologia", res.tipologia)
    m2.metric("Completude", f"{res.completude:.0f}%" if res.dossie else "—")
    m3.metric("Campos faltantes", len(res.campos_faltantes))
    m4.metric("Confiança", res.classificacao.get("confianca", "—"))

    if res.dossie:
        painel_lacunas(res.dossie, banco)

    if res.campos_faltantes:
        st.warning("Preencher no editor: " + ", ".join(res.campos_faltantes))

    with st.expander("Trilha do pipeline, entidades e anexos lidos"):
        t1, t2, t3 = st.tabs(["Trilha", "Entidades", "Anexos"])
        with t1:
            for passo in res.trilha:
                st.text(passo)
            st.json(res.classificacao)
        with t2:
            st.json(res.entidades)
        with t3:
            for e in res.extracoes:
                st.markdown(f"**{e.nome}** — `{e.origem}`"
                            + (f" — {e.paginas} pág." if e.paginas else "")
                            + (f" — ⚠ {e.erro}" if e.erro else ""))
                st.text_area(e.nome, e.markdown[:8000], height=170,
                             key=f"anx_{e.nome}")

    st.info("Documento carregado no **Editor**. Abra a aba para revisar e salvar.")


# --------------------------------------------------------------------------- #
# ABA 2 — EDITOR
# --------------------------------------------------------------------------- #

def aba_editor(banco: Banco, cfg: dict) -> None:
    st.markdown(ed.css_folha(), unsafe_allow_html=True)

    if not st.session_state.get("corpo_html"):
        st.info("Nenhum documento aberto. Gere um na aba **Redigir** ou reabra "
                "um da **Galeria**.")
        return

    meta = st.session_state["meta"]
    doc_id = st.session_state.get("doc_id")
    estados = ["rascunho", "revisado", "expedido"]

    topo = st.columns([2, 1, 2, 1.4, 1.2])
    meta["servidor"] = topo[0].text_input("Servidor", meta.get("servidor", ""))
    meta["matricula"] = topo[1].text_input("Matrícula", meta.get("matricula", ""))
    meta["assunto"] = topo[2].text_input("Assunto", meta.get("assunto", ""))
    meta["processo"] = topo[3].text_input("Processo", meta.get("processo", ""))
    meta["status"] = topo[4].selectbox(
        "Status", estados,
        index=estados.index(meta.get("status", "rascunho")))
    st.session_state["meta"] = meta

    with st.expander("Cabeçalho e rodapé"):
        cab, rod = st.columns(2)
        st.session_state["cabecalho"] = cab.text_area(
            "Cabeçalho (HTML)", st.session_state["cabecalho"], height=110)
        st.session_state["rodape"] = rod.text_area(
            "Rodapé (HTML)", st.session_state["rodape"], height=110)
        r1, r2 = st.columns(2)
        if r1.button("Restaurar cabeçalho padrão", use_container_width=True):
            st.session_state["cabecalho"] = ed.CABECALHO_PADRAO
            st.rerun()
        if r2.button("Restaurar rodapé padrão", use_container_width=True):
            st.session_state["rodape"] = ed.RODAPE_PADRAO
            st.rerun()

    ordem_status = ["rascunho", "revisado", "expedido"]
    ac1, ac2, ac3, ac4 = st.columns(4)
    if ac1.button("⏩ Avançar status", use_container_width=True,
                  help="rascunho → revisado → expedido"):
        i = ordem_status.index(meta.get("status", "rascunho"))
        meta["status"] = ordem_status[min(i + 1, len(ordem_status) - 1)]
        st.session_state["meta"] = meta
        if doc_id:
            banco.atualizar_documento(
                doc_id, st.session_state["corpo_html"],
                ed.html_para_texto(st.session_state["corpo_html"]),
                st.session_state["cabecalho"], st.session_state["rodape"],
                nota=f"status → {meta['status']}", status=meta["status"])
        st.rerun()

    with ac2.popover("🧹 Apagar texto", use_container_width=True):
        st.write("Limpar todo o corpo do documento? O conteúdo atual continua "
                 "recuperável nas versões salvas.")
        if st.button("Confirmar limpeza", type="primary"):
            st.session_state["corpo_html"] = "<p></p>"
            st.rerun()

    if ac3.button("↩ Recarregar da última versão", use_container_width=True,
                  disabled=not doc_id):
        d = banco.documento(doc_id)
        st.session_state["corpo_html"] = d["corpo_html"]
        st.rerun()

    if ac4.button("＋ Inserir lacunas pendentes", use_container_width=True,
                  disabled=not st.session_state.get("dossie")):
        dossie = st.session_state["dossie"]
        bloco = "".join(
            f'<p><mark class="faltante">[DADO FALTANTE: {c}]</mark> — {gaps.pista(c)}</p>'
            for c in dossie.lacunas)
        st.session_state["corpo_html"] += (
            "<p><strong>PENDÊNCIAS A PREENCHER</strong></p>" + bloco)
        st.rerun()

    aba_edit, aba_prev = st.tabs(["✎ Editar", "👁 Pré-visualizar folha"])
    with aba_edit:
        if TEM_QUILL:
            novo = st_quill(value=st.session_state["corpo_html"], html=True,
                            toolbar=ed.TOOLBAR_QUILL, key="quill_editor")
            if novo is not None:
                st.session_state["corpo_html"] = novo
        else:
            st.warning("`streamlit-quill` não instalado — editando HTML bruto. "
                       "Rode: pip install streamlit-quill")
            st.session_state["corpo_html"] = st.text_area(
                "Conteúdo (HTML)", st.session_state["corpo_html"], height=460)
    with aba_prev:
        st.markdown(ed.folha_html(st.session_state["corpo_html"],
                                  st.session_state["cabecalho"],
                                  st.session_state["rodape"]),
                    unsafe_allow_html=True)

    st.divider()
    corpo_html = st.session_state["corpo_html"]
    corpo_txt = ed.html_para_texto(corpo_html)
    res = st.session_state.get("resultado")
    tipologia = res.tipologia if res else (meta.get("tipologia") or "DOCUMENTO")

    a1, a2, a3, a4 = st.columns(4)

    with a1:
        rotulo = "💾 Salvar no banco" if not doc_id else "💾 Salvar nova versão"
        if st.button(rotulo, type="primary", use_container_width=True):
            if doc_id:
                v = banco.atualizar_documento(
                    doc_id, corpo_html, corpo_txt,
                    st.session_state["cabecalho"], st.session_state["rodape"],
                    nota="edição no editor", status=meta["status"],
                    servidor=meta["servidor"], matricula=meta["matricula"],
                    assunto=meta["assunto"], processo=meta["processo"])
                st.success(f"Versão {v} gravada (documento #{doc_id}).")
            else:
                dados = {
                    "tipologia": tipologia,
                    "materia": (res.classificacao.get("materia") if res else ""),
                    "situacao": (res.classificacao.get("situacao") if res else ""),
                    "modelos": (res.modelos_usados if res else []),
                    "campos_faltantes": (res.campos_faltantes if res else []),
                    "entidades": (res.entidades if res else {}),
                    "classificacao": (res.classificacao if res else {}),
                    "provedores": (res.provedores if res else []),
                    "corpo_html": corpo_html, "corpo_texto": corpo_txt,
                    "cabecalho": st.session_state["cabecalho"],
                    "rodape": st.session_state["rodape"],
                }
                dados.update(meta)
                doc_id = banco.salvar_documento(dados)
                st.session_state["doc_id"] = doc_id
                if res and res.extracoes:
                    banco.salvar_anexos(doc_id, res.extracoes)
                st.success(f"Documento #{doc_id} salvo no SQLite — visível na Galeria.")
            st.session_state["ultimo_salvo"] = dt.datetime.now(TZ).strftime("%H:%M:%S")

    with a2:
        if st.button("⬇ Gerar .docx", use_container_width=True):
            arq = exporters.nome_arquivo(meta["matricula"], meta["servidor"],
                                         meta["assunto"], tipologia)
            destino = ed.html_para_docx(corpo_html, SAIDA_DIR / f"{arq}.docx",
                                        st.session_state["cabecalho"],
                                        st.session_state["rodape"])
            if doc_id:
                banco.atualizar_documento(
                    doc_id, corpo_html, corpo_txt, st.session_state["cabecalho"],
                    st.session_state["rodape"], nota="exportado para .docx",
                    docx_path=str(destino))
            st.session_state["docx_bytes"] = destino.read_bytes()
            st.session_state["docx_nome"] = destino.name
            st.success(f"Gerado: {destino.name}")
        if st.session_state.get("docx_bytes"):
            st.download_button("Baixar .docx", st.session_state["docx_bytes"],
                               file_name=st.session_state["docx_nome"],
                               use_container_width=True)

    with a3:
        if st.button("☁ Enviar ao Google Docs", use_container_width=True):
            if not cfg.get("pasta_raiz"):
                st.error("Informe o ID da pasta-raiz na barra lateral.")
            else:
                try:
                    info = exporters.enviar_google_docs(
                        corpo_txt, cfg["sa"], cfg["pasta_raiz"],
                        meta["matricula"], meta["servidor"], meta["assunto"],
                        tipologia)
                    if doc_id:
                        banco.atualizar_documento(
                            doc_id, corpo_html, corpo_txt,
                            st.session_state["cabecalho"],
                            st.session_state["rodape"],
                            nota="enviado ao Google Drive",
                            drive_id=info["id"], drive_link=info["link"],
                            arquivo_nome=info["arquivo"])
                    if cfg.get("planilha") and doc_id:
                        registro = banco.documento(doc_id)
                        completude = (st.session_state["dossie"].completude
                                      if st.session_state.get("dossie") else 0.0)
                        sheets.registrar_documento(cfg["sa"], cfg["planilha"],
                                                   registro, completude)
                        faltantes = json.loads(registro["campos_faltantes"] or "[]")
                        sheets.registrar_lacunas(
                            cfg["sa"], cfg["planilha"], doc_id, meta["servidor"],
                            meta["matricula"], faltantes,
                            {c: gaps.pista(c) for c in faltantes})
                        st.caption("Linha gravada na planilha do Drive.")
                    st.success(f"Criado em {info['pasta']}")
                    st.markdown(f"[Abrir no Drive]({info['link']})")
                except Exception as exc:
                    st.error(f"Falha no envio: {exc}")

    with a4:
        st.download_button("⬇ Markdown", corpo_txt, file_name="documento.md",
                           mime="text/markdown", use_container_width=True)

    if st.session_state.get("ultimo_salvo"):
        st.caption(f"Último salvamento: {st.session_state['ultimo_salvo']}"
                   + (f" · documento #{doc_id}" if doc_id else ""))

    if doc_id:
        with st.expander("Histórico de versões deste documento"):
            versoes = banco.versoes(doc_id)
            st.dataframe(versoes, use_container_width=True, hide_index=True)
            if versoes:
                alvo = st.selectbox("Restaurar versão",
                                    [v["versao"] for v in versoes], key="restaurar")
                if st.button("Carregar versão no editor"):
                    v = banco.versao(doc_id, alvo)
                    st.session_state["corpo_html"] = v["corpo_html"]
                    st.session_state["cabecalho"] = v["cabecalho"] or ""
                    st.session_state["rodape"] = v["rodape"] or ""
                    st.rerun()


# --------------------------------------------------------------------------- #
# ABA 3 — GALERIA
# --------------------------------------------------------------------------- #

def aba_galeria(banco: Banco) -> None:
    st.markdown("#### Galeria de documentos salvos")

    f1, f2, f3, f4 = st.columns([3, 1.4, 1.4, 1.2])
    busca = f1.text_input("Buscar (servidor, matrícula, assunto, processo, conteúdo)")
    tipologia = f2.selectbox("Tipologia", ["(todas)", "INFORMACAO", "DESPACHO",
                                           "OFICIO", "MEMORANDO", "MANIFESTACAO",
                                           "REQUERIMENTO"])
    status = f3.selectbox("Status", ["(todos)", "rascunho", "revisado", "expedido"])
    f4.markdown("<br>", unsafe_allow_html=True)
    if f4.button("Atualizar", use_container_width=True):
        st.rerun()

    registros = banco.listar_documentos(
        busca=busca,
        tipologia="" if tipologia == "(todas)" else tipologia,
        status="" if status == "(todos)" else status)

    if not registros:
        st.info("Nenhum documento encontrado.")
        return

    st.caption(f"{len(registros)} documento(s)")
    st.dataframe(
        [{"#": r["id"], "Atualizado": r["atualizado_em"][:16].replace("T", " "),
          "Tipologia": r["tipologia"], "Servidor": r["servidor"],
          "Matrícula": r["matricula"], "Assunto": r["assunto"],
          "Processo": r["processo"], "Status": r["status"],
          "Ver.": r["versao_atual"],
          "Faltantes": len(json.loads(r["campos_faltantes"] or "[]")),
          "Drive": "sim" if r["drive_link"] else ""}
         for r in registros],
        use_container_width=True, hide_index=True)

    st.divider()
    alvo = st.selectbox(
        "Abrir documento", registros,
        format_func=lambda r: (f"#{r['id']} · {r['tipologia']} · "
                               f"{r['servidor'] or 's/ servidor'} · "
                               f"{r['assunto'] or 's/ assunto'}"))
    if not alvo:
        return

    doc = banco.documento(alvo["id"])
    st.markdown(ed.css_folha(), unsafe_allow_html=True)
    st.markdown(ed.folha_html(doc["corpo_html"], doc["cabecalho"], doc["rodape"]),
                unsafe_allow_html=True)

    g1, g2, g3, g4 = st.columns(4)
    if g1.button("✎ Abrir no editor", type="primary", use_container_width=True):
        st.session_state["doc_id"] = doc["id"]
        st.session_state["corpo_html"] = doc["corpo_html"]
        st.session_state["cabecalho"] = doc["cabecalho"] or ed.CABECALHO_PADRAO
        st.session_state["rodape"] = doc["rodape"] or ed.RODAPE_PADRAO
        st.session_state["meta"] = {
            "servidor": doc["servidor"] or "", "matricula": doc["matricula"] or "",
            "assunto": doc["assunto"] or "", "processo": doc["processo"] or "",
            "status": doc["status"] or "rascunho",
            "tipologia": doc["tipologia"],
        }
        st.session_state["resultado"] = None
        st.success("Carregado. Abra a aba **Editor**.")

    with g2:
        if st.button("⬇ Gerar .docx", use_container_width=True):
            arq = (doc["arquivo_nome"] or f"documento_{doc['id']}") + ".docx"
            destino = ed.html_para_docx(doc["corpo_html"], SAIDA_DIR / arq,
                                        doc["cabecalho"], doc["rodape"])
            st.download_button("Baixar", destino.read_bytes(),
                               file_name=destino.name, use_container_width=True)

    if doc["drive_link"]:
        g3.markdown(f"[☁ Abrir no Drive]({doc['drive_link']})")

    with g4.popover("🗑 Excluir", use_container_width=True):
        st.write(f"Excluir o documento #{doc['id']} e todas as suas versões?")
        if st.button("Confirmar exclusão", type="primary"):
            banco.excluir_documento(doc["id"])
            st.rerun()

    with st.expander("Versões, anexos e metadados"):
        v1, v2, v3 = st.tabs(["Versões", "Anexos", "Metadados"])
        with v1:
            st.dataframe(banco.versoes(doc["id"]), use_container_width=True,
                         hide_index=True)
        with v2:
            anexos = banco.anexos(doc["id"])
            if anexos:
                for a in anexos:
                    st.markdown(f"**{a['nome']}** — `{a['origem']}`"
                                + (f" — {a['paginas']} pág." if a["paginas"] else ""))
                    st.text_area(a["nome"], (a["markdown"] or "")[:6000],
                                 height=150, key=f"gal_anx_{a['id']}")
            else:
                st.caption("Sem anexos gravados.")
        with v3:
            st.json({k: doc[k] for k in ("modelos", "campos_faltantes",
                                         "classificacao", "provedores", "hash")})


# --------------------------------------------------------------------------- #
# ABA 4 — BASE DE CONHECIMENTO
# --------------------------------------------------------------------------- #

def aba_base(pool: KeyPool, banco: Banco, cfg: dict) -> None:
    st.markdown("#### Base de conhecimento")
    st.caption("Suba um PDF: o LlamaParse converte para Markdown, o modelo cataloga "
               "o frontmatter e o arquivo entra no banco e em kb/.")

    up = st.file_uploader("Documentos para internalizar",
                          type=["pdf", "docx", "odt", "txt", "md"],
                          accept_multiple_files=True, key="up_kb")
    c1, c2 = st.columns([2, 1])
    base_alvo = c1.selectbox("Base de destino",
                             ["(o modelo decide)"] + list(ingest.BASES))
    c2.markdown("<br>", unsafe_allow_html=True)
    gravar_disco = c2.checkbox("Gravar .md em kb/", value=True,
                               help="Permite versionar no GitHub")

    if st.button("▶  INTERNALIZAR NA BASE", type="primary",
                 disabled=not up, use_container_width=True):
        arquivos = [(a.name, a.getvalue()) for a in up]
        barra = st.progress(0, text="Iniciando...")
        resultados = ingest.ingerir_lote(
            pool, banco, arquivos, KB_DIR,
            base_forcada="" if base_alvo.startswith("(") else base_alvo,
            ordem=cfg.get("ordem"),
            progresso=lambda p, m: barra.progress(min(p, 100), text=m))
        barra.empty()
        for r in resultados:
            if r.ok:
                st.success(f"{r.identificador} · {r.natureza} · `{r.origem_extracao}`"
                           + (f" · {r.paginas} pág." if r.paginas else "")
                           + f" → {r.caminho}")
                with st.expander(f"Frontmatter de {r.identificador}"):
                    st.json(r.frontmatter)
            else:
                st.error(f"Falha: {r.erro}")
        st.cache_data.clear()

    st.divider()
    registros = banco.listar_kb(apenas_ativos=False)
    st.caption(f"{len(registros)} arquivo(s) na base")
    st.dataframe(
        [{"#": r["id"], "ID": r["identificador"], "Base": r["base"],
          "Tipologia": r["tipologia"], "Matéria": r["materia"],
          "Origem": r["origem"], "Fonte": r["arquivo_fonte"],
          "Ativo": bool(r["ativo"]), "Bytes": r["tam"]} for r in registros],
        use_container_width=True, hide_index=True)

    alvo = st.selectbox("Inspecionar", ["(nenhum)"] +
                        [f"{r['id']} · {r['identificador']}" for r in registros])
    if alvo != "(nenhum)":
        kb_id = int(alvo.split(" · ")[0])
        reg = banco.kb_conteudo(kb_id)
        i1, i2, i3 = st.columns(3)
        if i1.button("Desativar" if reg["ativo"] else "Ativar",
                     use_container_width=True):
            banco.alternar_kb(kb_id, not reg["ativo"])
            st.rerun()
        if i2.button("Excluir da base", use_container_width=True):
            banco.excluir_kb(kb_id)
            st.rerun()
        i3.download_button("⬇ Baixar .md", reg["conteudo_md"],
                           file_name=Path(reg["caminho"]).name,
                           use_container_width=True)
        st.code(reg["conteudo_md"][:12000], language="markdown")

    st.divider()
    s1, s2 = st.columns(2)
    if s1.button("↺ Sincronizar kb/ → banco", use_container_width=True):
        n = banco.sincronizar_kb_do_disco(KB_DIR)
        st.success(f"{n} arquivo(s) internalizados.")
        st.cache_data.clear()
    if s2.button("↻ Exportar banco → kb/", use_container_width=True):
        n = banco.exportar_kb_para_disco(KB_DIR)
        st.success(f"{n} arquivo(s) gravados em kb/.")
        st.cache_data.clear()

    st.divider()
    st.markdown("##### Pacote para o GitHub")
    st.caption("Zip com todos os .md ativos, INDEX.md navegável, catalogo.json "
               "e .gitignore — pronto para commit.")
    g1, g2 = st.columns([1, 2])
    incluir = g1.checkbox("Incluir documentos gerados", value=False)
    if g2.button("📦 Gerar pacote .zip", type="primary", use_container_width=True):
        destino = exportar_pacote_github(banco, SAIDA_DIR / "kb_github.zip",
                                         incluir_documentos=incluir)
        st.session_state["zip_github"] = destino.read_bytes()
        st.success(f"Pacote gerado: {destino.name} "
                   f"({destino.stat().st_size // 1024} KB)")
    if st.session_state.get("zip_github"):
        st.download_button("⬇ Baixar pacote GitHub",
                           st.session_state["zip_github"],
                           file_name="kb_cocarreira.zip", mime="application/zip",
                           use_container_width=True)


# --------------------------------------------------------------------------- #
# ABA 5 — SISTEMA
# --------------------------------------------------------------------------- #

def aba_sistema(pool: KeyPool, banco: Banco) -> None:
    st.markdown("#### Chaves de API")
    c1, c2, c3, c4 = st.columns([1.3, 2, 1.2, 1])
    prov = c1.selectbox("Provedor", list(PROVIDERS.keys()),
                        format_func=lambda p: f"{p} ({PROVIDERS[p]['papel']})")
    chave = c2.text_input("Chave", type="password")
    rotulo = c3.text_input("Rótulo", value="chave-1")
    c4.markdown("<br>", unsafe_allow_html=True)
    if c4.button("Adicionar", use_container_width=True):
        ok, msg = pool.add(prov, chave.strip(), rotulo)
        (st.success if ok else st.error)(f"{prov}: {msg}")
        st.rerun()

    resumo = pool.resumo()
    if resumo:
        st.dataframe(resumo, use_container_width=True, hide_index=True)
        r1, r2 = st.columns([2, 1])
        alvo = r1.selectbox("Remover chave", ["(nenhuma)"] +
                            [f"{l['provedor']} · {l['rotulo']}" for l in resumo])
        r2.markdown("<br>", unsafe_allow_html=True)
        if alvo != "(nenhuma)" and r2.button("Remover", use_container_width=True):
            p, rot = alvo.split(" · ", 1)
            for k in pool.data.get(p, []):
                if k.get("label") == rot:
                    pool.remove(p, k["key"])
                    break
            st.rerun()

    e1, e2 = st.columns(2)
    e1.download_button("⬇ Exportar chaves (JSON)", pool.export_json(),
                       file_name="api_keys.json", mime="application/json",
                       use_container_width=True)
    imp = e2.file_uploader("Importar chaves (JSON)", type=["json"], key="imp_sis")
    if imp is not None and e2.button("Aplicar importação", use_container_width=True):
        st.success(f"{pool.import_json(imp.read())} chave(s) importada(s).")
        st.rerun()

    st.divider()
    st.markdown("#### Banco de dados")
    est = banco.estatisticas()
    cols = st.columns(len(est))
    for col, (k, v) in zip(cols, est.items()):
        col.metric(k.replace("_", " ").title(), v)

    d1, d2, d3 = st.columns(3)
    if ARQ_DB.exists():
        d1.download_button("⬇ Baixar redator.db", ARQ_DB.read_bytes(),
                           file_name="redator.db", use_container_width=True)
    esquema = APP_DIR / "schema.yml"
    if esquema.exists():
        d2.download_button("⬇ Baixar schema.yml",
                           esquema.read_text(encoding="utf-8"),
                           file_name="schema.yml", use_container_width=True)
    d3.download_button("⬇ Exportar documentos (JSON)",
                       json.dumps(banco.listar_documentos(limite=5000),
                                  ensure_ascii=False, indent=2),
                       file_name="documentos.json", mime="application/json",
                       use_container_width=True)

    st.divider()
    st.markdown("#### Planilha no Google Drive")
    sheet_id = banco.get_config("sheet_id", "")
    sa_path = banco.get_config("sa_path", "")
    if not sheet_id:
        st.info("Nenhuma planilha vinculada. Crie pela barra lateral "
                "(Google Drive / Sheets).")
    else:
        st.caption(f"Planilha vinculada: `{sheet_id}`")
        p1, p2 = st.columns(2)
        if p1.button("↻ Sincronizar aba Servidores", use_container_width=True):
            try:
                with banco.conn() as c:
                    linhas = [dict(r) for r in c.execute(
                        """SELECT s.matricula, s.nome, s.cargo, s.unidade,
                                  COUNT(d.id) AS qtd_documentos,
                                  MAX(d.criado_em) AS ultima_movimentacao,
                                  s.atualizado_em, s.observacoes
                           FROM servidores s
                           LEFT JOIN documentos d ON d.matricula = s.matricula
                           GROUP BY s.matricula ORDER BY s.nome""").fetchall()]
                n = sheets.sincronizar_servidores(sa_path, sheet_id, linhas)
                st.success(f"{n} servidor(es) sincronizados.")
            except Exception as exc:
                st.error(f"Falha: {exc}")
        if p2.button("👁 Ler aba Documentos", use_container_width=True):
            try:
                st.dataframe(sheets.ler_aba(sa_path, sheet_id, "Documentos"),
                             use_container_width=True, hide_index=True)
            except Exception as exc:
                st.error(f"Falha: {exc}")

    with st.expander("Log técnico"):
        st.dataframe(banco.eventos(150), use_container_width=True, hide_index=True)


# --------------------------------------------------------------------------- #
# MAIN
# --------------------------------------------------------------------------- #

def main() -> None:
    st.set_page_config(page_title="Redator COCARREIRA", layout="wide",
                       initial_sidebar_state="expanded", page_icon="📄")
    init_estado()
    pool = _pool()
    banco = _banco()
    docs = carregar_docs()
    cfg = barra_lateral(pool, banco, docs)

    st.title("Redator de Documentos Oficiais — COCARREIRA/CAEDNC")

    t1, t2, t3, t4, t5 = st.tabs(
        ["Redigir", "Editor", "Galeria", "Base de conhecimento", "Sistema"])
    with t1:
        aba_redigir(pool, banco, docs, cfg)
    with t2:
        aba_editor(banco, cfg)
    with t3:
        aba_galeria(banco)
    with t4:
        aba_base(pool, banco, cfg)
    with t5:
        aba_sistema(pool, banco)


if __name__ == "__main__":
    main()
