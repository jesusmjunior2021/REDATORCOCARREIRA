#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/pipeline.py — Orquestracao do fluxo completo.

    ANEXOS ─► [1] LlamaParse ─► markdown fiel
                    │
                    ▼
              [2] Groq/Cerebras ─► extracao estruturada (JSON de entidades)
                    │
                    ▼
              [3] Groq/Cerebras ─► classificacao da tipologia (fuzzy + arvore de decisao)
                    │
                    ▼
              [4] Python + .md   ─► montagem e redacao da peca final
                    │
                    ▼
              [5] .docx / Google Docs / planilha

Filosofia: SEM ESTRUTURA RIGIDA. Nenhuma etapa exige formulario preenchido. O que
o operador digitar em linguagem natural e o que os anexos trouxerem bastam. Campo
nao localizado vira literalmente [DADO FALTANTE: <campo>] — nunca e inventado.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import kb as kbmod
from . import llm
from . import parsing
from .keys import KeyPool, TZ

MESES = ["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]

TIPOLOGIAS = ("INFORMACAO", "INFORMAÇÃO", "DESPACHO", "OFICIO", "OFÍCIO",
              "MEMORANDO", "MANIFESTACAO", "MANIFESTAÇÃO", "REQUERIMENTO")


def data_extenso(quando: dt.datetime | None = None) -> str:
    q = quando or dt.datetime.now(TZ)
    return f"{q.day} de {MESES[q.month - 1]} de {q.year}"


# --------------------------------------------------------------------------- #
# RESULTADO
# --------------------------------------------------------------------------- #

@dataclass
class ResultadoPipeline:
    documento: str = ""
    entidades: dict = field(default_factory=dict)
    classificacao: dict = field(default_factory=dict)
    modelos_usados: list[str] = field(default_factory=list)
    campos_faltantes: list[str] = field(default_factory=list)
    extracoes: list[parsing.ParseResult] = field(default_factory=list)
    trilha: list[str] = field(default_factory=list)
    provedores: list[str] = field(default_factory=list)

    @property
    def hash(self) -> str:
        return hashlib.sha256(self.documento.encode("utf-8")).hexdigest()[:12]

    @property
    def tipologia(self) -> str:
        m = re.search(r"^\s*(" + "|".join(TIPOLOGIAS) + r")\s*$",
                      self.documento, re.MULTILINE | re.IGNORECASE)
        if m:
            return m.group(1).upper()
        return (self.classificacao.get("tipologia") or "DOCUMENTO").upper()


# --------------------------------------------------------------------------- #
# ETAPA 1 — EXTRACAO DOS ANEXOS
# --------------------------------------------------------------------------- #

def etapa_parse(pool: KeyPool, anexos: list[tuple[str, bytes]],
                instrucao: str = parsing.INSTRUCAO_PADRAO,
                progresso=None) -> tuple[list[parsing.ParseResult], str]:
    if not anexos:
        return [], ""
    if progresso:
        progresso(10, f"Extraindo {len(anexos)} anexo(s) com LlamaParse...")
    resultados = parsing.parse_lote(pool, anexos, instrucao)
    return resultados, parsing.consolidar(resultados)


# --------------------------------------------------------------------------- #
# ETAPA 2 — EXTRACAO ESTRUTURADA DE ENTIDADES
# --------------------------------------------------------------------------- #

SYS_EXTRACAO = (
    "Voce e um extrator de entidades de processos administrativos do Tribunal de "
    "Justica do Maranhao. Responda EXCLUSIVAMENTE com um objeto JSON valido, sem "
    "preambulo, sem comentario e sem cerca de codigo. Nunca invente valor: campo "
    "nao encontrado no material recebe null. Copie os valores exatamente como "
    "aparecem no documento, sem corrigir, resumir ou normalizar."
)

SCHEMA_ENTIDADES = """{
  "servidores": [
    {"nome": null, "matricula": null, "cargo": null,
     "unidade_origem": null, "unidade_destino": null, "papel": "requerente|permutante|indicado"}
  ],
  "processo": {"numero": null, "assunto": null, "objeto": null},
  "requerente": {"nome": null, "cargo": null, "tipo": "servidor|gestor|magistrado|desembargador"},
  "pecas_referenciadas": {"oficio": null, "despacho": null, "decisao": null,
                          "manifestacao": null, "informa": null, "id_movimentacao": null,
                          "codigo_validacao": null},
  "portarias": [],
  "instrucao_processual": {
    "anuencia_chefia_origem": "favoravel|desfavoravel|ausente|nao_informado",
    "anuencia_chefia_destino": "favoravel|desfavoravel|ausente|nao_informado",
    "certidao_pad": "negativa|positiva|ausente|nao_informado",
    "dossie_mentorh": "juntado|ausente|nao_informado",
    "ultima_movimentacao_data": null,
    "vaga_confirmada": "sim|nao|nao_informado"
  },
  "auxilio_bolsa": {
    "edital": null, "curso": null, "ies": null, "modalidade": null,
    "periodo_curso": null, "mensalidade_contratada": null,
    "mensalidade_paga_semestre_anterior": null, "mensalidade_paga_semestre_atual": null,
    "mes_reajuste": null, "valor_bruto_antigo": null, "valor_bruto_novo": null,
    "periodo_meses": null, "primeira_concessao": "sim|nao|nao_informado",
    "linhas_por_mes": []
  },
  "datas": {"requerimento": null, "documento": null},
  "observacoes_relevantes": []
}"""


def etapa_entidades(pool: KeyPool, relato: str, material: str,
                    ordem: list[str] | None = None, progresso=None) -> tuple[dict, str]:
    if progresso:
        progresso(30, "Estruturando entidades (Groq/Cerebras)...")
    user = f"""SCHEMA DE SAIDA (preencha; use null onde nao houver dado):
{SCHEMA_ENTIDADES}

RELATO DO OPERADOR:
{relato or '(sem relato)'}

MATERIAL EXTRAIDO DOS ANEXOS:
{material or '(sem anexos)'}

Extraia as entidades. Responda apenas o JSON."""
    r = llm.completar(pool, SYS_EXTRACAO, user, ordem, max_tokens=4000, json_mode=True)
    try:
        return llm.json_da_resposta(r.texto), f"{r.provedor}/{r.modelo}"
    except ValueError:
        return {"_erro_parse": r.texto[:2000]}, f"{r.provedor}/{r.modelo}"


# --------------------------------------------------------------------------- #
# ETAPA 3 — CLASSIFICACAO DA TIPOLOGIA
# --------------------------------------------------------------------------- #

SYS_CLASSIFICACAO = (
    "Voce e o classificador de tipologia documental da COCARREIRA/CAEDNC do TJMA. "
    "Aplique as arvores de decisao fornecidas. Responda EXCLUSIVAMENTE com JSON valido."
)

SCHEMA_CLASSIFICACAO = """{
  "modelos": ["ID do modelo principal", "ID da peca-par se houver"],
  "tipologia": "INFORMACAO|DESPACHO|OFICIO|MEMORANDO|MANIFESTACAO|REQUERIMENTO",
  "materia": "",
  "situacao": "",
  "confianca": 0.0,
  "justificativa": "uma frase",
  "travas": {
    "intersticio_6_meses": "cumprido|violado|nao_verificavel",
    "intersticio_2_anos": "cumprido|violado|nao_aplicavel|nao_verificavel",
    "certidao_pad": "ok|pendente|nao_verificavel",
    "anuencia_chefias": "ok|pendente|desfavoravel|nao_verificavel",
    "impacto_primeiro_grau": "sem_impacto|alertar|nao_verificavel"
  },
  "opinar_pelo_deferimento": true,
  "alertas": []
}"""


def etapa_classificar(pool: KeyPool, docs: list[kbmod.Documento], relato: str,
                      entidades: dict, pre_selecao: list[str],
                      ordem: list[str] | None = None,
                      progresso=None) -> tuple[dict, str]:
    if progresso:
        progresso(50, "Classificando a tipologia documental...")
    contexto = kbmod.montar_contexto(docs, pre_selecao, incluir_catalogo=True,
                                     limite_chars=60_000)
    user = f"""BASE DE CONHECIMENTO (catalogo, normas e arvores de decisao):
{contexto}

PRE-SELECAO FUZZY (candidatos mais provaveis, em ordem):
{', '.join(pre_selecao) or '(nenhum)'}

RELATO DO OPERADOR:
{relato or '(sem relato)'}

ENTIDADES EXTRAIDAS:
{entidades}

TAREFA: percorra a arvore de decisao aplicavel e devolva o JSON abaixo.
Regra dura: se qualquer trava do NIVEL 3 estiver 'violado' ou 'pendente',
"opinar_pelo_deferimento" deve ser false e a peca sera de remessa para diligencia.
Se a confianca for inferior a 0.90, liste as hipoteses concorrentes em "alertas".

SCHEMA:
{SCHEMA_CLASSIFICACAO}

Responda apenas o JSON."""
    r = llm.completar(pool, SYS_CLASSIFICACAO, user, ordem, max_tokens=2500, json_mode=True)
    try:
        cls = llm.json_da_resposta(r.texto)
    except ValueError:
        cls = {"modelos": pre_selecao[:1], "confianca": 0.0,
               "justificativa": "falha ao interpretar a classificacao; "
                                "usada a pre-selecao fuzzy",
               "alertas": ["classificacao automatica indisponivel"]}
    return cls, f"{r.provedor}/{r.modelo}"


# --------------------------------------------------------------------------- #
# ETAPA 4 — REDACAO
# --------------------------------------------------------------------------- #

def _system_redacao(prompt_mestre: Path | None) -> str:
    if prompt_mestre and Path(prompt_mestre).exists():
        return Path(prompt_mestre).read_text(encoding="utf-8")
    return ("Voce e o redator de pecas administrativas da COCARREIRA/CAEDNC do TJMA. "
            "Temperature 0.2. Reproduza o modelo sem alterar a ordem dos paragrafos. "
            "Nunca invente dado: campo ausente vira [DADO FALTANTE: <campo>].")


def etapa_redigir(pool: KeyPool, docs: list[kbmod.Documento], relato: str,
                  entidades: dict, classificacao: dict, material: str,
                  prompt_mestre: Path | None = None,
                  ordem: list[str] | None = None,
                  instrucoes_extra: str = "",
                  progresso=None) -> tuple[str, str]:
    if progresso:
        progresso(75, "Redigindo a peca...")

    ids = classificacao.get("modelos") or []
    ids = [i for i in ids if kbmod.por_id(docs, i)]
    contexto = kbmod.montar_contexto(docs, ids, incluir_catalogo=False)
    campos = kbmod.campos_de(docs, ids)

    travas = classificacao.get("travas", {})
    opinar = classificacao.get("opinar_pelo_deferimento", True)

    user = f"""MODELOS SELECIONADOS: {', '.join(ids) or '(nenhum — use MOD-GEN-01)'}
CAMPOS OBRIGATORIOS DESSES MODELOS: {', '.join(campos) or '(nao declarados)'}

BASE DE CONHECIMENTO (modelos, normas e regras):
{contexto}

ENTIDADES EXTRAIDAS DOS ANEXOS E DO RELATO:
{entidades}

CLASSIFICACAO:
{classificacao}

MATERIAL BRUTO EXTRAIDO (consulte para conferir valores literais):
{material[:40000] or '(sem anexos)'}

RELATO DO OPERADOR:
{relato or '(sem relato)'}

DATA CORRENTE: {data_extenso()}

INSTRUCOES DE REDACAO
1. Reproduza o(s) modelo(s) sem alterar a ordem dos paragrafos.
2. Substitua cada {{CAMPO}} pelo valor real. Campo ausente vira literalmente
   [DADO FALTANTE: <nome do campo>]. Nunca suponha nome, matricula, valor, edital,
   numero de processo, portaria, manifestacao ou informa.
3. Se houver peca-par, entregue as duas em blocos separados e identificados, na
   ordem canonica (MANIFESTACAO antes de OFICIO; INFORMACAO antes de DESPACHO).
4. opinar_pelo_deferimento = {opinar}. Se for false, NAO opine pelo deferimento:
   redija a remessa para diligencia, indicando a trava pendente. Travas: {travas}
5. Calcule e resolva todo valor (nunca deixe formula). Auxilio-bolsa: 70% do valor
   efetivamente pago, arredondado a 2 casas, limitado ao teto da PORT-GP 1045/2022.
6. Nao comprima dados: todo dado fornecido deve aparecer na peca.
{instrucoes_extra}

Encerre com o rodape tecnico:
Tipo classificado: ...
Modelo-base utilizado: ...
Norma invocada: ...
Semestre de referencia: ... (apenas auxilio-bolsa)
Campos faltantes: ...

Entregue apenas o documento e o rodape."""

    r = llm.completar(pool, _system_redacao(prompt_mestre), user, ordem, max_tokens=8000)
    return r.texto.strip(), f"{r.provedor}/{r.modelo}"


# --------------------------------------------------------------------------- #
# PIPELINE COMPLETO
# --------------------------------------------------------------------------- #

FALTANTE_RE = re.compile(r"\[DADO FALTANTE:\s*([^\]]+)\]")


def executar(pool: KeyPool, docs: list[kbmod.Documento], relato: str,
             anexos: list[tuple[str, bytes]] | None = None,
             modelos_forcados: list[str] | None = None,
             ordem_inferencia: list[str] | None = None,
             prompt_mestre: Path | None = None,
             instrucao_parse: str = parsing.INSTRUCAO_PADRAO,
             instrucoes_extra: str = "",
             progresso=None) -> ResultadoPipeline:
    """Roda o fluxo inteiro. `progresso(pct, msg)` e opcional."""
    res = ResultadoPipeline()

    # 1 — parsing
    extracoes, material = etapa_parse(pool, anexos or [], instrucao_parse, progresso)
    res.extracoes = extracoes
    res.trilha.append(
        f"[1] LlamaParse: {len(extracoes)} anexo(s) — "
        f"{', '.join(sorted({e.origem for e in extracoes})) or 'nenhum'}")

    # 2 — entidades
    entidades, prov2 = etapa_entidades(pool, relato, material, ordem_inferencia, progresso)
    res.entidades = entidades
    res.provedores.append(prov2)
    res.trilha.append(f"[2] Extracao estruturada via {prov2}")

    # 3 — classificacao
    if modelos_forcados:
        classificacao = {
            "modelos": kbmod.resolver_pares(docs, modelos_forcados),
            "confianca": 1.0,
            "justificativa": "modelo indicado manualmente pelo operador",
            "travas": {}, "opinar_pelo_deferimento": True, "alertas": [],
        }
        res.trilha.append(f"[3] Classificacao manual: {', '.join(classificacao['modelos'])}")
    else:
        consulta = f"{relato}\n{entidades}"
        pre = [d.id for d, _ in kbmod.pre_selecionar(docs, consulta, limite=6)]
        res.trilha.append(f"[3a] Pre-selecao fuzzy: {', '.join(pre) or 'nenhuma'}")
        classificacao, prov3 = etapa_classificar(pool, docs, relato, entidades, pre,
                                                 ordem_inferencia, progresso)
        classificacao["modelos"] = kbmod.resolver_pares(
            docs, classificacao.get("modelos") or pre[:1])
        res.provedores.append(prov3)
        res.trilha.append(
            f"[3b] Classificacao via {prov3} — confianca "
            f"{classificacao.get('confianca', 0)}")
    res.classificacao = classificacao
    res.modelos_usados = classificacao.get("modelos", [])

    # 4 — redacao
    texto, prov4 = etapa_redigir(pool, docs, relato, entidades, classificacao,
                                 material, prompt_mestre, ordem_inferencia,
                                 instrucoes_extra, progresso)
    res.documento = texto
    res.provedores.append(prov4)
    res.trilha.append(f"[4] Redacao via {prov4}")
    res.campos_faltantes = sorted({m.strip() for m in FALTANTE_RE.findall(texto)})

    if progresso:
        progresso(100, "Concluido.")
    return res
