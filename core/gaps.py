#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/gaps.py — Extracao DIRIGIDA as lacunas do modelo selecionado.

Diferenca em relacao a extracao generica:

  generica  -> "leia este PDF e me diga o que tem nele"
  dirigida  -> "neste PDF, procure ESPECIFICAMENTE por MATRICULA, VLR_PAGO,
               EDITAL e MES_REAJUSTE; para cada um devolva o valor literal,
               a pagina e o trecho onde encontrou; se nao houver, diga null"

O alvo vem do frontmatter `campos_obrigatorios` do .md que o usuario escolheu
(ou que o classificador escolheu). O LlamaParse recebe uma parsing_instruction
montada com esses campos, o que muda o comportamento do OCR/layout: ele preserva
as regioes onde esses dados costumam estar (tabelas de mensalidade, cabecalho de
matricula, rodape de portaria) em vez de resumir.

Depois da extracao, cada anexo vira um .md de EVIDENCIAS — formato enxuto que o
LLM de redacao processa muito melhor do que o PDF bruto — e recebe um percentual
de completude: quantos dos campos-alvo aquele documento sozinho conseguiu suprir.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import kb as kbmod
from . import llm, parsing
from .keys import KeyPool

# --------------------------------------------------------------------------- #
# DESCRICAO DOS CAMPOS — ajuda o extrator a saber o que procurar
# --------------------------------------------------------------------------- #

PISTAS: dict[str, str] = {
    "NOME": "nome completo do servidor, como grafado no requerimento ou no dossie",
    "MATRICULA": "numero de matricula funcional, geralmente 4 a 7 digitos",
    "CARGO": "cargo efetivo (ex.: Tecnico Judiciario, Auxiliar Judiciario, Oficial de Justica)",
    "UNIDADE_ORIGEM": "unidade/vara/comarca onde o servidor esta lotado hoje",
    "UNIDADE_DESTINO": "unidade/vara/comarca para onde pretende ir",
    "NUM_PROCESSO": "numero do processo administrativo, formato NNNNN/AAAA",
    "NUM_MANIF": "numero da MANIF-CAEDNC",
    "NUM_INFORMA": "numero do INFORMA-CAEDNC",
    "NUM_DECISAO": "numero da DECISAO-GP",
    "COD_VALIDACAO": "codigo de validacao do documento no DigiDoc",
    "ID_MOVIMENTACAO": "ID da movimentacao no DigiDoc",
    "OFC_REFERENCIA": "numero do oficio de referencia citado nos autos",
    "DATA": "data do documento, por extenso ou numerica",
    "DATA_OFICIO": "data de expedicao do oficio",
    "EDITAL": "numero e ano do edital EDT-GDG de convocacao",
    "CURSO": "nome do curso de graduacao ou pos-graduacao",
    "IES": "nome da instituicao de ensino superior",
    "MODALIDADE": "modalidade do curso: presencial, EAD, semipresencial",
    "PERIODO_CURSO": "periodo/semestre em que o aluno esta matriculado",
    "VLR_CONTRATADO": "valor da mensalidade contratada, conforme o contrato",
    "VLR_PAGO": "valor da mensalidade EFETIVAMENTE PAGA, ja com descontos",
    "VLR_PAGO_ANTERIOR": "mensalidade efetivamente paga no semestre ANTERIOR",
    "VLR_PAGO_NOVO": "mensalidade efetivamente paga no semestre ATUAL",
    "VLR_BRUTO_ANTIGO": "valor bruto da mensalidade antes do reajuste, sem descontos",
    "VLR_BRUTO_NOVO": "valor bruto da mensalidade depois do reajuste, sem descontos",
    "MES_REAJUSTE": "mes e ano a partir do qual a mensalidade mudou",
    "PERIODO_MESES": "intervalo de meses comprovado (ex.: janeiro a junho de 2026)",
    "LINHAS_POR_MES": "tabela mes a mes com mensalidade contratada e efetivamente paga",
    "REQUERENTE": "quem formula o pedido (servidor, gestor, magistrado)",
    "AUTORIDADE": "autoridade que requer ou determina",
    "MOTIVO": "motivo alegado no pedido ou na devolucao",
    "HISTORICO_MOVIMENTACOES": "cadeia de relotacoes/remocoes com numero e ano das portarias",
    "LISTA_SERVIDORES": "relacao de servidores com nome, cargo, matricula e unidades",
}

# Campos que o sistema resolve sozinho — nunca contam como lacuna real
AUTOPREENCHIVEIS = {"DATA", "DATA_OFICIO"}

CALCULADOS = {"VLR_70PCT", "VLR_70PCT_NOVO"}


def pista(campo: str) -> str:
    if campo in PISTAS:
        return PISTAS[campo]
    legivel = campo.replace("_", " ").lower()
    return f"campo '{legivel}' conforme aparece no documento"


# --------------------------------------------------------------------------- #
# ESTRUTURAS
# --------------------------------------------------------------------------- #

@dataclass
class Achado:
    campo: str
    valor: str | None = None
    pagina: str = ""
    trecho: str = ""
    confianca: float = 0.0
    fonte: str = ""              # nome do anexo

    @property
    def encontrado(self) -> bool:
        return bool(self.valor) and str(self.valor).strip().lower() not in (
            "null", "none", "nao informado", "n/a", "-", "")


@dataclass
class EvidenciaDocumento:
    nome: str
    origem: str
    paginas: int = 0
    markdown_bruto: str = ""
    markdown_evidencias: str = ""
    achados: list[Achado] = field(default_factory=list)
    erro: str = ""

    @property
    def supridos(self) -> list[str]:
        return [a.campo for a in self.achados if a.encontrado]

    def completude(self, alvos: list[str]) -> float:
        if not alvos:
            return 0.0
        return round(100.0 * len(set(self.supridos) & set(alvos)) / len(alvos), 1)


@dataclass
class Dossie:
    alvos: list[str] = field(default_factory=list)
    documentos: list[EvidenciaDocumento] = field(default_factory=list)
    consolidado: dict[str, Achado] = field(default_factory=dict)

    @property
    def preenchidos(self) -> list[str]:
        return [c for c, a in self.consolidado.items() if a.encontrado]

    @property
    def lacunas(self) -> list[str]:
        return [c for c in self.alvos
                if c not in self.preenchidos and c not in AUTOPREENCHIVEIS]

    @property
    def completude(self) -> float:
        exigiveis = [c for c in self.alvos if c not in AUTOPREENCHIVEIS]
        if not exigiveis:
            return 100.0
        ok = len([c for c in exigiveis if c in self.preenchidos])
        return round(100.0 * ok / len(exigiveis), 1)

    def markdown(self) -> str:
        """Dossie consolidado em .md — e isto que vai para o redator."""
        linhas = ["# DOSSIE DE EVIDENCIAS", "",
                  f"Completude geral: **{self.completude}%** "
                  f"({len(self.preenchidos)}/{len(self.alvos)} campos-alvo)", "",
                  "## CAMPOS LOCALIZADOS", "",
                  "| Campo | Valor | Fonte | Pag. | Trecho |",
                  "|---|---|---|---|---|"]
        for campo in self.alvos:
            a = self.consolidado.get(campo)
            if a and a.encontrado:
                trecho = (a.trecho or "").replace("|", "/")[:90]
                linhas.append(f"| {campo} | {a.valor} | {a.fonte} | {a.pagina} | {trecho} |")
        if self.lacunas:
            linhas += ["", "## LACUNAS — NAO LOCALIZADAS NOS ANEXOS", "",
                       "Estes campos devem sair como [DADO FALTANTE: X] "
                       "ou ser informados manualmente:", ""]
            linhas += [f"- **{c}** — {pista(c)}" for c in self.lacunas]
        linhas += ["", "## COMPLETUDE POR DOCUMENTO", "",
                   "| Documento | Extracao | Pag. | Campos supridos | Completude |",
                   "|---|---|---|---|---|"]
        for d in self.documentos:
            linhas.append(f"| {d.nome} | {d.origem} | {d.paginas or '-'} | "
                          f"{len(d.supridos)} | {d.completude(self.alvos)}% |")
        return "\n".join(linhas)


# --------------------------------------------------------------------------- #
# ALVOS
# --------------------------------------------------------------------------- #

def alvos_do_modelo(docs: list[kbmod.Documento], ids: list[str]) -> list[str]:
    """Campos-alvo = campos_obrigatorios dos modelos, menos os calculados."""
    campos = kbmod.campos_de(docs, ids)
    return [c for c in campos if c not in CALCULADOS]


# --------------------------------------------------------------------------- #
# INSTRUCAO DIRIGIDA PARA O LLAMAPARSE
# --------------------------------------------------------------------------- #

def instrucao_dirigida(alvos: list[str], tipologia: str = "",
                       materia: str = "") -> str:
    """Monta a parsing_instruction que guia o LlamaParse aos campos-alvo."""
    if not alvos:
        return parsing.INSTRUCAO_PADRAO

    lista = "\n".join(f"- {c}: {pista(c)}" for c in alvos[:28])
    contexto = ""
    if tipologia or materia:
        contexto = (f"O documento sera usado para redigir um(a) {tipologia} "
                    f"sobre {materia}. ")

    return (
        "Este e um documento administrativo do Poder Judiciario do Maranhao. "
        f"{contexto}"
        "PRIORIDADE MAXIMA: localizar e preservar, com fidelidade literal, os "
        "seguintes dados, que serao usados para preencher lacunas de uma peca:\n"
        f"{lista}\n\n"
        "Regras de extracao:\n"
        "1. Onde qualquer um desses dados aparecer, transcreva a regiao inteira "
        "sem resumir, incluindo rotulo e valor.\n"
        "2. Converta TODA tabela em tabela Markdown, linha a linha, sem omitir "
        "nenhuma — tabelas de mensalidade e de movimentacao funcional sao criticas.\n"
        "3. Marque a mudanca de pagina com <!-- pagina N -->.\n"
        "4. Preserve numeros, datas e valores monetarios exatamente como grafados, "
        "inclusive pontuacao e simbolo de moeda.\n"
        "5. Nao resuma, nao interprete, nao corrija e nao normalize o conteudo.\n"
        "6. Se o documento for manuscrito ou carimbado, transcreva o que for legivel "
        "e marque o ilegivel como [ILEGIVEL]."
    )


# --------------------------------------------------------------------------- #
# EXTRACAO DIRIGIDA POR DOCUMENTO
# --------------------------------------------------------------------------- #

SYS_ALVO = (
    "Voce e um localizador de dados em documentos administrativos do TJMA. "
    "Recebe uma lista de campos-alvo e o texto de UM documento. Para cada campo, "
    "devolve o valor literal encontrado, a pagina e o trecho de apoio. "
    "Responda EXCLUSIVAMENTE com JSON valido. "
    "Se o campo nao estiver no documento, valor = null. NUNCA deduza, "
    "NUNCA calcule, NUNCA complete com conhecimento externo: copie o que esta escrito."
)


def _schema_alvo(alvos: list[str]) -> str:
    itens = ",\n    ".join(
        f'"{c}": {{"valor": null, "pagina": "", "trecho": "", "confianca": 0.0}}'
        for c in alvos)
    return "{\n  \"achados\": {\n    " + itens + "\n  }\n}"


def caçar_campos(pool: KeyPool, nome: str, markdown: str, alvos: list[str],
                 ordem: list[str] | None = None) -> list[Achado]:
    """Segunda passagem: o LLM varre o Markdown atras dos campos-alvo."""
    if not alvos or not markdown.strip():
        return []

    descricao = "\n".join(f"- {c}: {pista(c)}" for c in alvos)
    user = f"""DOCUMENTO: {nome}

CAMPOS-ALVO A LOCALIZAR:
{descricao}

TEXTO DO DOCUMENTO:
{markdown[:60000]}

Para cada campo-alvo, devolva:
  valor     — exatamente como grafado no documento, ou null se ausente
  pagina    — o numero indicado por <!-- pagina N -->, ou "" se nao houver
  trecho    — ate 120 caracteres em volta do achado, para auditoria
  confianca — 0.0 a 1.0

SCHEMA:
{_schema_alvo(alvos)}

Responda apenas o JSON."""

    try:
        r = llm.completar(pool, SYS_ALVO, user, ordem, max_tokens=4000, json_mode=True)
        bruto = llm.json_da_resposta(r.texto).get("achados", {})
    except Exception:                                          # noqa: BLE001
        return []

    achados: list[Achado] = []
    for campo in alvos:
        item = bruto.get(campo) or {}
        if not isinstance(item, dict):
            item = {"valor": item}
        achados.append(Achado(
            campo=campo,
            valor=(str(item.get("valor")).strip()
                   if item.get("valor") not in (None, "", "null") else None),
            pagina=str(item.get("pagina") or ""),
            trecho=str(item.get("trecho") or "")[:200],
            confianca=float(item.get("confianca") or 0.0),
            fonte=nome))
    return achados


def evidencias_para_md(nome: str, alvos: list[str],
                       achados: list[Achado], markdown: str) -> str:
    """Reduz o documento a um .md de evidencias — enxuto e citavel."""
    linhas = [f"# EVIDENCIAS — {nome}", ""]
    encontrados = [a for a in achados if a.encontrado]
    if encontrados:
        linhas += ["| Campo | Valor | Pag. | Confianca |", "|---|---|---|---|"]
        for a in encontrados:
            linhas.append(f"| {a.campo} | {a.valor} | {a.pagina or '-'} | "
                          f"{a.confianca:.2f} |")
        linhas += ["", "## TRECHOS DE APOIO", ""]
        for a in encontrados:
            if a.trecho:
                linhas.append(f"- **{a.campo}**: …{a.trecho}…")
    else:
        linhas.append("_Nenhum campo-alvo localizado neste documento._")

    ausentes = [a.campo for a in achados if not a.encontrado]
    if ausentes:
        linhas += ["", f"## NAO LOCALIZADOS AQUI", "", ", ".join(ausentes)]

    # tabelas do documento sao preservadas na integra: costumam conter os valores
    tabelas = [l for l in markdown.split("\n") if l.strip().startswith("|")]
    if tabelas:
        linhas += ["", "## TABELAS DO DOCUMENTO (integrais)", ""] + tabelas[:120]

    return "\n".join(linhas)


# --------------------------------------------------------------------------- #
# ORQUESTRACAO
# --------------------------------------------------------------------------- #

def levantar(pool: KeyPool, anexos: list[tuple[str, bytes]], alvos: list[str],
             tipologia: str = "", materia: str = "",
             ordem: list[str] | None = None,
             conhecidos: dict[str, str] | None = None,
             progresso=None) -> Dossie:
    """
    Fluxo completo da caca as lacunas:
      1. monta a instrucao dirigida com os campos-alvo;
      2. roda o LlamaParse guiado, anexo por anexo;
      3. varre cada Markdown atras dos alvos;
      4. gera o .md de evidencias por documento;
      5. consolida, resolvendo conflito pela maior confianca.
    """
    dossie = Dossie(alvos=list(alvos))
    instrucao = instrucao_dirigida(alvos, tipologia, materia)
    total = max(len(anexos), 1)

    for i, (nome, blob) in enumerate(anexos, 1):
        if progresso:
            progresso(int(5 + 55 * (i - 1) / total),
                      f"[{i}/{total}] Extração dirigida em {nome}...")
        pr = parsing.parse_documento(pool, nome, blob, instrucao)
        doc = EvidenciaDocumento(nome=nome, origem=pr.origem, paginas=pr.paginas,
                                 markdown_bruto=pr.markdown, erro=pr.erro)
        if pr.ok:
            if progresso:
                progresso(int(5 + 55 * (i - 0.4) / total),
                          f"[{i}/{total}] Caçando {len(alvos)} campos em {nome}...")
            doc.achados = caçar_campos(pool, nome, pr.markdown, alvos, ordem)
            doc.markdown_evidencias = evidencias_para_md(
                nome, alvos, doc.achados, pr.markdown)
        else:
            doc.markdown_evidencias = f"# EVIDENCIAS — {nome}\n\n[FALHA: {pr.erro}]"
        dossie.documentos.append(doc)

    # consolidacao: melhor confianca vence
    for doc in dossie.documentos:
        for a in doc.achados:
            if not a.encontrado:
                continue
            atual = dossie.consolidado.get(a.campo)
            if atual is None or a.confianca > atual.confianca:
                dossie.consolidado[a.campo] = a

    # o que o operador digitou tem precedencia sobre o extraido
    for campo, valor in (conhecidos or {}).items():
        if valor and str(valor).strip():
            dossie.consolidado[campo] = Achado(
                campo=campo, valor=str(valor).strip(), fonte="informado pelo operador",
                confianca=1.0)
        if campo not in dossie.alvos:
            dossie.alvos.append(campo)

    if progresso:
        progresso(65, f"Completude: {dossie.completude}% — "
                      f"{len(dossie.lacunas)} lacuna(s)")
    return dossie


def salvar_evidencias(dossie: Dossie, destino_dir: Path,
                      prefixo: str = "") -> list[Path]:
    """Grava os .md de evidencias em disco — prontos para commit no GitHub."""
    destino_dir = Path(destino_dir)
    destino_dir.mkdir(parents=True, exist_ok=True)
    escritos: list[Path] = []
    base = f"{prefixo}_" if prefixo else ""

    p = destino_dir / f"{base}DOSSIE.md"
    p.write_text(dossie.markdown(), encoding="utf-8")
    escritos.append(p)

    for d in dossie.documentos:
        slug = re.sub(r"[^\w.-]+", "_", Path(d.nome).stem)[:60]
        p = destino_dir / f"{base}EVID_{slug}.md"
        p.write_text(d.markdown_evidencias, encoding="utf-8")
        escritos.append(p)
    return escritos
