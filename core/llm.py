#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/llm.py — ETAPA 2 do pipeline: inferencia em Groq / Cerebras / Grok (xAI) / Gemini.

Todos os provedores expoem interface compativel com OpenAI /chat/completions, o que
permite um unico cliente com rodizio transparente de chave e de provedor.

Saida low temperature: temperature 0.2, top_p 1.0, penalidades 0.0.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

import requests

from .keys import KeyPool, PROVIDERS, ORDEM_PADRAO_INFERENCIA

TEMPERATURE = 0.2
TOP_P = 1.0
TIMEOUT = 240


@dataclass
class Resposta:
    texto: str
    provedor: str
    modelo: str
    tentativas: int
    tokens: dict


class SemApiDisponivel(RuntimeError):
    pass


def completar(pool: KeyPool, system: str, user: str,
              ordem: list[str] | None = None,
              modelo: str | None = None,
              max_tokens: int = 8000,
              json_mode: bool = False) -> Resposta:
    """
    Percorre os provedores na ordem dada; dentro de cada um, todas as chaves ativas.
    Levanta SemApiDisponivel se nenhuma combinacao funcionar.
    """
    ordem = ordem or ORDEM_PADRAO_INFERENCIA
    ultimo_erro = "nenhuma chave de inferencia cadastrada"
    tentativas = 0

    for provedor in ordem:
        cfg = PROVIDERS.get(provedor)
        if not cfg or cfg.get("papel") != "inferencia":
            continue
        tentadas: set[str] = set()

        while True:
            entry = pool.next_key(provedor)
            if entry is None or entry["key"] in tentadas:
                break
            tentadas.add(entry["key"])
            tentativas += 1

            mdl = modelo if (modelo and modelo in cfg["models"]) else cfg["models"][0]
            payload = {
                "model": mdl,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": TEMPERATURE,
                "top_p": TOP_P,
                "max_tokens": max_tokens,
            }
            if json_mode:
                payload["response_format"] = {"type": "json_object"}

            try:
                r = requests.post(
                    cfg["chat"],
                    headers={"Authorization": f"Bearer {entry['key']}",
                             "Content-Type": "application/json"},
                    json=payload, timeout=TIMEOUT)
            except requests.RequestException as exc:
                ultimo_erro = f"{provedor}: rede — {exc}"
                continue

            if r.status_code == 200:
                pool.marcar_uso(provedor, entry["key"])
                data = r.json()
                texto = data["choices"][0]["message"]["content"] or ""
                return Resposta(texto, provedor, mdl, tentativas,
                                data.get("usage", {}) or {})

            if r.status_code in (429, 402):
                pool.marcar_cota(provedor, entry["key"])
                ultimo_erro = f"{provedor}: cota esgotada — alternando chave"
                continue

            if r.status_code in (401, 403):
                pool.marcar_invalida(provedor, entry["key"], f"HTTP {r.status_code}")
                ultimo_erro = f"{provedor}: chave rejeitada"
                continue

            if r.status_code == 400 and json_mode:
                # provedor sem suporte a response_format — repete sem json_mode
                payload.pop("response_format", None)
                try:
                    r2 = requests.post(
                        cfg["chat"],
                        headers={"Authorization": f"Bearer {entry['key']}",
                                 "Content-Type": "application/json"},
                        json=payload, timeout=TIMEOUT)
                    if r2.status_code == 200:
                        pool.marcar_uso(provedor, entry["key"])
                        data = r2.json()
                        return Resposta(data["choices"][0]["message"]["content"] or "",
                                        provedor, mdl, tentativas,
                                        data.get("usage", {}) or {})
                except requests.RequestException:
                    pass

            ultimo_erro = f"{provedor}: HTTP {r.status_code} — {r.text[:200]}"

    raise SemApiDisponivel(
        f"Falha em todos os provedores apos {tentativas} tentativa(s). "
        f"Ultimo erro: {ultimo_erro}")


# --------------------------------------------------------------------------- #
# UTILITARIO: extrair JSON de resposta suja
# --------------------------------------------------------------------------- #

_CERCA = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def json_da_resposta(texto: str) -> dict:
    """Extrai o primeiro objeto JSON valido da resposta, tolerando cercas e preambulo."""
    candidatos: list[str] = []
    m = _CERCA.search(texto)
    if m:
        candidatos.append(m.group(1))
    candidatos.append(texto)

    ini = texto.find("{")
    fim = texto.rfind("}")
    if ini != -1 and fim > ini:
        candidatos.append(texto[ini:fim + 1])

    for c in candidatos:
        try:
            return json.loads(c.strip())
        except json.JSONDecodeError:
            continue
    raise ValueError("nao foi possivel extrair JSON da resposta do modelo")
