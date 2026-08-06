#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/keys.py — Pool de chaves de API com rodizio, cooldown e import/export JSON.

Provedores suportados:
  llamaparse  — LlamaCloud / LlamaParse (extracao de documentos complexos)
  groq        — Groq Cloud (inferencia rapida)
  cerebras    — Cerebras Inference
  xai         — xAI / Grok
  gemini      — Google AI Studio (camada compativel OpenAI)

Regra de rodizio:
  - dentro de um provedor, usa-se a chave ATIVA de menor contador de uso;
  - HTTP 429/402 (cota) -> cooldown temporario, salta para a proxima chave;
  - HTTP 401/403 -> chave marcada invalida e removida do rodizio;
  - esgotado o provedor, salta para o proximo da ordem de prioridade.
Enquanto houver uma chave viva em qualquer provedor, o usuario nao fica sem API.
"""

from __future__ import annotations

import json
import time
import datetime as dt
from pathlib import Path

import requests

TZ = dt.timezone(dt.timedelta(hours=-3))  # America/Fortaleza

# --------------------------------------------------------------------------- #
# CATALOGO DE PROVEDORES
# --------------------------------------------------------------------------- #

PROVIDERS: dict[str, dict] = {
    "llamaparse": {
        "papel": "parsing",
        "base": "https://api.cloud.llamaindex.ai/api/v1",
        "validate": "https://api.cloud.llamaindex.ai/api/v1/parsing/supported_file_extensions",
        "models": [],
    },
    "groq": {
        "papel": "inferencia",
        "chat": "https://api.groq.com/openai/v1/chat/completions",
        "validate": "https://api.groq.com/openai/v1/models",
        "models": [
            "llama-3.3-70b-versatile",
            "openai/gpt-oss-120b",
            "llama-3.1-8b-instant",
        ],
    },
    "cerebras": {
        "papel": "inferencia",
        "chat": "https://api.cerebras.ai/v1/chat/completions",
        "validate": "https://api.cerebras.ai/v1/models",
        "models": [
            "llama-3.3-70b",
            "qwen-3-235b-a22b-instruct-2507",
            "llama3.1-8b",
        ],
    },
    "xai": {
        "papel": "inferencia",
        "chat": "https://api.x.ai/v1/chat/completions",
        "validate": "https://api.x.ai/v1/models",
        "models": ["grok-4", "grok-3-mini"],
    },
    "gemini": {
        "papel": "inferencia",
        "chat": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "validate": "https://generativelanguage.googleapis.com/v1beta/openai/models",
        "models": ["gemini-2.5-flash", "gemini-2.5-pro"],
    },
}

ORDEM_PADRAO_INFERENCIA = ["groq", "cerebras", "xai", "gemini"]

COOLDOWN_COTA_SEG = 900  # 15 minutos


# --------------------------------------------------------------------------- #
# PERSISTENCIA
# --------------------------------------------------------------------------- #

class KeyPool:
    """Pool persistente de chaves. Estrutura em disco:
    {provider: [{key, label, status, usos, cooldown_until, ultimo_erro}]}
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.data: dict[str, list[dict]] = self._load()

    # ---------------- io ----------------

    def _load(self) -> dict[str, list[dict]]:
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                return {p: raw.get(p, []) for p in PROVIDERS}
            except json.JSONDecodeError:
                pass
        return {p: [] for p in PROVIDERS}

    def save(self) -> None:
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def export_json(self) -> str:
        return json.dumps(self.data, ensure_ascii=False, indent=2)

    def import_json(self, blob: str | bytes) -> int:
        """Mescla um JSON exportado. Nao duplica chaves ja presentes."""
        if isinstance(blob, bytes):
            blob = blob.decode("utf-8")
        incoming = json.loads(blob)
        novas = 0
        for prov, keys in incoming.items():
            if prov not in PROVIDERS:
                continue
            existentes = {k["key"] for k in self.data.get(prov, [])}
            for k in keys:
                if k.get("key") and k["key"] not in existentes:
                    self.data.setdefault(prov, []).append({
                        "key": k["key"],
                        "label": k.get("label", "importada"),
                        "status": k.get("status", "ativa"),
                        "usos": int(k.get("usos", 0)),
                        "cooldown_until": 0,
                        "ultimo_erro": "",
                    })
                    novas += 1
        self.save()
        return novas

    # ---------------- gestao ----------------

    def add(self, provider: str, key: str, label: str = "chave",
            validar: bool = True) -> tuple[bool, str]:
        if provider not in PROVIDERS:
            return False, f"provedor desconhecido: {provider}"
        if any(k["key"] == key for k in self.data.get(provider, [])):
            return False, "chave ja cadastrada"
        if validar:
            ok, msg = self.validate(provider, key)
            if not ok:
                return False, msg
        self.data.setdefault(provider, []).append({
            "key": key, "label": label, "status": "ativa",
            "usos": 0, "cooldown_until": 0, "ultimo_erro": "",
        })
        self.save()
        return True, "chave validada e adicionada"

    def remove(self, provider: str, key: str) -> None:
        self.data[provider] = [k for k in self.data.get(provider, []) if k["key"] != key]
        self.save()

    @staticmethod
    def validate(provider: str, key: str) -> tuple[bool, str]:
        """Valida chamando o endpoint mais barato do provedor."""
        cfg = PROVIDERS.get(provider)
        if not cfg:
            return False, "provedor desconhecido"
        try:
            r = requests.get(cfg["validate"],
                             headers={"Authorization": f"Bearer {key}",
                                      "accept": "application/json"},
                             timeout=25)
        except requests.RequestException as exc:
            return False, f"rede: {exc}"
        if r.status_code == 200:
            return True, "valida"
        if r.status_code in (401, 403):
            return False, "chave rejeitada pelo provedor"
        return False, f"HTTP {r.status_code}: {r.text[:160]}"

    # ---------------- rodizio ----------------

    def next_key(self, provider: str) -> dict | None:
        agora = time.time()
        vivos = [k for k in self.data.get(provider, [])
                 if k.get("status") == "ativa" and k.get("cooldown_until", 0) <= agora]
        if not vivos:
            return None
        vivos.sort(key=lambda k: k.get("usos", 0))
        return vivos[0]

    def marcar_uso(self, provider: str, key: str) -> None:
        for k in self.data.get(provider, []):
            if k["key"] == key:
                k["usos"] = k.get("usos", 0) + 1
        self.save()

    def marcar_cota(self, provider: str, key: str,
                    segundos: int = COOLDOWN_COTA_SEG) -> None:
        for k in self.data.get(provider, []):
            if k["key"] == key:
                k["cooldown_until"] = time.time() + segundos
                k["ultimo_erro"] = "cota esgotada (429/402)"
        self.save()

    def marcar_invalida(self, provider: str, key: str, motivo: str) -> None:
        for k in self.data.get(provider, []):
            if k["key"] == key:
                k["status"] = "invalida"
                k["ultimo_erro"] = motivo
        self.save()

    def disponiveis(self, provider: str) -> int:
        agora = time.time()
        return sum(1 for k in self.data.get(provider, [])
                   if k.get("status") == "ativa" and k.get("cooldown_until", 0) <= agora)

    def resumo(self) -> list[dict]:
        agora = time.time()
        linhas = []
        for prov, keys in self.data.items():
            for k in keys:
                cd = k.get("cooldown_until", 0)
                estado = k.get("status", "?")
                if estado == "ativa" and cd > agora:
                    estado = f"cooldown ate {dt.datetime.fromtimestamp(cd, TZ):%H:%M:%S}"
                linhas.append({
                    "provedor": prov,
                    "papel": PROVIDERS[prov]["papel"],
                    "rotulo": k.get("label", ""),
                    "estado": estado,
                    "usos": k.get("usos", 0),
                    "ultimo_erro": k.get("ultimo_erro", ""),
                })
        return linhas
