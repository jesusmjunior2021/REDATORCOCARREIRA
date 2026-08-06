#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/kb.py — Base de conhecimento .md, sem estrutura rigida.

Os modelos de redacao sao os .md das duas pastas (01_BASE_RH_AUXILIO_BOLSA e
02_BASE_GERAL_DOCUMENTOS). Este modulo:
  - carrega todos os .md e le o frontmatter;
  - separa modelos redigiveis (com `tipologia`) de arquivos normativos/logicos;
  - faz pre-selecao fuzzy por similaridade lexica, para reduzir o contexto enviado
    ao LLM sem impor um formulario fixo;
  - monta o pacote de contexto que vai para a etapa de redacao.

Regra de projeto: a pre-selecao fuzzy NUNCA descarta os arquivos sempre-presentes
(normas, arvores de decisao, dicionario de campos, regras). Elas sao o piso legal.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

TIPOS_SEMPRE_PRESENTES = {
    "norma",
    "logica_de_classificacao",
    "regras_operacionais",
    "dicionario_de_dados",
}

STOPWORDS = {
    "de", "da", "do", "das", "dos", "e", "o", "a", "os", "as", "em", "no", "na",
    "para", "por", "com", "que", "um", "uma", "ao", "aos", "se", "sua", "seu",
    "sobre", "pela", "pelo", "the", "of",
}


# --------------------------------------------------------------------------- #
# MODELO
# --------------------------------------------------------------------------- #

@dataclass
class Documento:
    caminho: str
    base: str
    id: str
    texto: str
    meta: dict = field(default_factory=dict)

    @property
    def tipologia(self) -> str:
        return self.meta.get("tipologia", "")

    @property
    def materia(self) -> str:
        return self.meta.get("materia") or self.meta.get("evento", "")

    @property
    def situacao(self) -> str:
        return self.meta.get("situacao", "")

    @property
    def par(self) -> str:
        return self.meta.get("par", "")

    @property
    def campos(self) -> list[str]:
        c = self.meta.get("campos_obrigatorios", [])
        return c if isinstance(c, list) else [c]

    @property
    def redigivel(self) -> bool:
        return bool(self.tipologia)

    @property
    def sempre_presente(self) -> bool:
        return self.meta.get("tipo", "") in TIPOS_SEMPRE_PRESENTES

    @property
    def rotulo(self) -> str:
        partes = [self.id, self.tipologia, self.materia]
        if self.situacao:
            partes.append(self.situacao)
        return " — ".join(p for p in partes if p)


# --------------------------------------------------------------------------- #
# CARGA
# --------------------------------------------------------------------------- #

def _parse_frontmatter(texto: str) -> dict:
    m = FRONTMATTER.match(texto)
    if not m:
        return {}
    meta: dict = {}
    for linha in m.group(1).splitlines():
        if ":" not in linha or linha.strip().startswith("#"):
            continue
        chave, valor = linha.split(":", 1)
        chave, valor = chave.strip(), valor.strip()
        if valor.startswith("[") and valor.endswith("]"):
            meta[chave] = [i.strip() for i in valor[1:-1].split(",") if i.strip()]
        else:
            meta[chave] = valor
    return meta


def carregar(kb_dir: str | Path) -> list[Documento]:
    kb_dir = Path(kb_dir)
    docs: list[Documento] = []
    if not kb_dir.exists():
        return docs
    for caminho in sorted(kb_dir.rglob("*.md")):
        texto = caminho.read_text(encoding="utf-8")
        meta = _parse_frontmatter(texto)
        docs.append(Documento(
            caminho=str(caminho.relative_to(kb_dir)),
            base=caminho.parent.name,
            id=meta.get("id", caminho.stem),
            texto=texto,
            meta=meta,
        ))
    return docs


def catalogo(docs: list[Documento]) -> list[Documento]:
    return [d for d in docs if d.redigivel]


def por_id(docs: list[Documento], ident: str) -> Documento | None:
    for d in docs:
        if d.id == ident:
            return d
    return None


def resolver_pares(docs: list[Documento], ids: list[str]) -> list[str]:
    """Se um modelo tem peca-par declarada, inclui a par automaticamente."""
    saida = list(dict.fromkeys(ids))
    for ident in list(saida):
        d = por_id(docs, ident)
        if d and d.par and d.par not in saida:
            saida.append(d.par)
    return saida


# --------------------------------------------------------------------------- #
# BUSCA FUZZY
# --------------------------------------------------------------------------- #

def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.lower()


def _tokens(texto: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{3,}", _normalizar(texto))
            if t not in STOPWORDS}


# Sinonimos e gatilhos do dominio: aproximam a linguagem do usuario da terminologia
# tecnica dos modelos, sem obrigar o usuario a saber o nome do instituto.
GATILHOS: dict[str, list[str]] = {
    "relotacao": ["relotar", "mudar de setor", "trocar de unidade", "mudanca de lotacao"],
    "exercicio": ["disposicao", "ficar a disposicao", "emprestar servidor", "ceder servidor"],
    "permuta": ["troca", "trocar de lugar", "permutar", "reciproco"],
    "remocao": ["remover", "mudar de comarca", "ir para outra cidade", "saude"],
    "devolucao": ["devolver servidor", "devolvido", "faltas", "nao quer mais"],
    "reconducao": ["reconduzir", "voltar ao cargo", "retornar ao tribunal", "ex-servidor"],
    "auxilio": ["bolsa", "mensalidade", "faculdade", "curso", "ies", "semestre",
                "renovacao", "implantacao", "70%"],
    "despacho": ["encaminhar", "abrir vista", "diligencia", "expedir portaria"],
    "oficio": ["comunicar", "coordenadoria de pagamento", "externo"],
    "memorando": ["digidoc", "resposta interna"],
    "requerimento": ["peticionar", "pedido do servidor", "formulario"],
}


def _expandir(consulta: str) -> set[str]:
    toks = _tokens(consulta)
    normal = _normalizar(consulta)
    for chave, frases in GATILHOS.items():
        if any(_normalizar(f) in normal for f in frases):
            toks.add(chave)
    return toks


def pontuar(doc: Documento, consulta_tokens: set[str]) -> float:
    """Similaridade fuzzy: pesa muito o frontmatter, pouco o corpo."""
    if not consulta_tokens:
        return 0.0
    cabecalho = _tokens(" ".join([
        doc.id, doc.tipologia, doc.materia, doc.situacao,
        " ".join(doc.meta.get("palavras_chave", []) or []),
        doc.meta.get("uso", ""), doc.caminho,
    ]))
    corpo = _tokens(doc.texto[:6000])

    inter_cab = len(consulta_tokens & cabecalho)
    inter_corpo = len(consulta_tokens & corpo)
    if inter_cab == 0 and inter_corpo == 0:
        return 0.0
    # Jaccard ponderado
    score = (3.0 * inter_cab / max(len(consulta_tokens | cabecalho), 1)
             + 1.0 * inter_corpo / max(len(consulta_tokens | corpo), 1))
    return round(score, 4)


def pre_selecionar(docs: list[Documento], consulta: str,
                   limite: int = 6, minimo: float = 0.02) -> list[tuple[Documento, float]]:
    """Ranqueia os modelos redigiveis mais provaveis para a consulta."""
    toks = _expandir(consulta)
    ranking = [(d, pontuar(d, toks)) for d in docs if d.redigivel]
    ranking = [(d, s) for d, s in ranking if s >= minimo]
    ranking.sort(key=lambda x: x[1], reverse=True)
    return ranking[:limite]


# --------------------------------------------------------------------------- #
# CONTEXTO PARA O LLM
# --------------------------------------------------------------------------- #

def montar_contexto(docs: list[Documento], ids_modelos: list[str],
                    incluir_catalogo: bool = True,
                    limite_chars: int = 90_000) -> str:
    """
    Monta o pacote enviado ao modelo:
      1. catalogo enxuto de tudo que existe (para o modelo saber o que pode escolher);
      2. arquivos sempre-presentes (normas, arvores, campos, regras) na integra;
      3. os modelos pre-selecionados na integra.
    """
    blocos: list[str] = []

    if incluir_catalogo:
        linhas = ["| ID | Tipologia | Materia | Situacao |", "|---|---|---|---|"]
        for d in catalogo(docs):
            linhas.append(f"| {d.id} | {d.tipologia} | {d.materia} | {d.situacao} |")
        blocos.append("===== CATALOGO COMPLETO DE MODELOS DISPONIVEIS =====\n"
                      + "\n".join(linhas))

    for d in docs:
        if d.sempre_presente:
            blocos.append(f"===== {d.caminho} =====\n{d.texto}")

    ids = set(resolver_pares(docs, ids_modelos))
    for d in docs:
        if d.id in ids and d.redigivel:
            blocos.append(f"===== {d.caminho} =====\n{d.texto}")

    texto = "\n\n".join(blocos)
    if len(texto) > limite_chars:
        texto = texto[:limite_chars] + "\n\n[CONTEXTO TRUNCADO POR LIMITE]"
    return texto


def campos_de(docs: list[Documento], ids: list[str]) -> list[str]:
    """Uniao ordenada dos campos obrigatorios dos modelos indicados."""
    campos: list[str] = []
    for ident in resolver_pares(docs, ids):
        d = por_id(docs, ident)
        if d:
            campos.extend(d.campos)
    return list(dict.fromkeys(campos))
