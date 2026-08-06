#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/db.py — Persistencia SQLite3 do Redator COCARREIRA.

Guarda TODA a documentacao produzida e toda a base de conhecimento:

  documentos        peca gerada (versao corrente) + metadados de arquivamento
  versoes           historico de edicoes de cada documento (auditoria)
  kb_arquivos       base de conhecimento .md internalizada (inclusive PDF convertido)
  anexos            material bruto extraido pelo LlamaParse, por documento
  servidores        cadastro derivado, para perfil e alerta de intersticio
  eventos           log tecnico do pipeline (provedores, tempos, erros)
  config            pares chave/valor da aplicacao

Nenhuma escrita destrutiva: editar um documento cria nova versao e atualiza o
ponteiro `versao_atual`. O conteudo anterior permanece recuperavel.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

TZ = dt.timezone(dt.timedelta(hours=-3))

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS documentos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    criado_em       TEXT NOT NULL,
    atualizado_em   TEXT NOT NULL,
    tipologia       TEXT NOT NULL,
    materia         TEXT,
    situacao        TEXT,
    modelos         TEXT,              -- JSON list de IDs .md
    servidor        TEXT,
    matricula       TEXT,
    assunto         TEXT,
    processo        TEXT,
    cabecalho       TEXT,              -- HTML do cabecalho editavel
    rodape          TEXT,
    corpo_html      TEXT NOT NULL,     -- conteudo do editor WYSIWYG
    corpo_texto     TEXT NOT NULL,     -- versao plana, para busca
    campos_faltantes TEXT,             -- JSON list
    entidades       TEXT,              -- JSON do extrator
    classificacao   TEXT,              -- JSON do classificador
    provedores      TEXT,              -- JSON list
    status          TEXT DEFAULT 'rascunho',   -- rascunho|revisado|expedido
    versao_atual    INTEGER DEFAULT 1,
    hash            TEXT,
    arquivo_nome    TEXT,
    drive_id        TEXT,
    drive_link      TEXT,
    docx_path       TEXT
);

CREATE TABLE IF NOT EXISTS versoes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    documento_id  INTEGER NOT NULL REFERENCES documentos(id) ON DELETE CASCADE,
    versao        INTEGER NOT NULL,
    criado_em     TEXT NOT NULL,
    corpo_html    TEXT NOT NULL,
    corpo_texto   TEXT NOT NULL,
    cabecalho     TEXT,
    rodape        TEXT,
    autor         TEXT DEFAULT 'operador',
    nota          TEXT,
    hash          TEXT
);

CREATE TABLE IF NOT EXISTS kb_arquivos (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    criado_em     TEXT NOT NULL,
    atualizado_em TEXT NOT NULL,
    identificador TEXT UNIQUE,         -- ID do frontmatter
    caminho       TEXT UNIQUE,         -- caminho relativo em kb/
    base          TEXT,                -- 01_BASE_... | 02_BASE_...
    tipologia     TEXT,
    materia       TEXT,
    situacao      TEXT,
    origem        TEXT,                -- manual|llamaparse|upload_md
    arquivo_fonte TEXT,                -- nome do PDF original, se houver
    conteudo_md   TEXT NOT NULL,
    frontmatter   TEXT,                -- JSON
    ativo         INTEGER DEFAULT 1,
    hash          TEXT
);

CREATE TABLE IF NOT EXISTS anexos (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    documento_id  INTEGER REFERENCES documentos(id) ON DELETE CASCADE,
    criado_em     TEXT NOT NULL,
    nome          TEXT NOT NULL,
    origem        TEXT,                -- llamaparse|pdfplumber|python-docx|odt|texto
    paginas       INTEGER DEFAULT 0,
    markdown      TEXT,
    erro          TEXT
);

CREATE TABLE IF NOT EXISTS servidores (
    matricula     TEXT PRIMARY KEY,
    nome          TEXT,
    cargo         TEXT,
    unidade       TEXT,
    atualizado_em TEXT,
    observacoes   TEXT
);

CREATE TABLE IF NOT EXISTS eventos (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    criado_em     TEXT NOT NULL,
    documento_id  INTEGER,
    etapa         TEXT,
    provedor      TEXT,
    duracao_seg   REAL,
    detalhe       TEXT,
    nivel         TEXT DEFAULT 'info'
);

CREATE TABLE IF NOT EXISTS config (
    chave  TEXT PRIMARY KEY,
    valor  TEXT
);

CREATE INDEX IF NOT EXISTS ix_doc_matricula ON documentos(matricula);
CREATE INDEX IF NOT EXISTS ix_doc_assunto   ON documentos(assunto);
CREATE INDEX IF NOT EXISTS ix_doc_tipologia ON documentos(tipologia);
CREATE INDEX IF NOT EXISTS ix_kb_base       ON kb_arquivos(base);
CREATE INDEX IF NOT EXISTS ix_ver_doc       ON versoes(documento_id);
"""

# Busca textual (FTS5) — opcional; se o SQLite nao tiver FTS5, seguimos com LIKE.
SCHEMA_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS documentos_fts USING fts5(
    servidor, matricula, assunto, processo, corpo_texto,
    content='documentos', content_rowid='id'
);
CREATE TRIGGER IF NOT EXISTS doc_ai AFTER INSERT ON documentos BEGIN
  INSERT INTO documentos_fts(rowid, servidor, matricula, assunto, processo, corpo_texto)
  VALUES (new.id, new.servidor, new.matricula, new.assunto, new.processo, new.corpo_texto);
END;
CREATE TRIGGER IF NOT EXISTS doc_ad AFTER DELETE ON documentos BEGIN
  INSERT INTO documentos_fts(documentos_fts, rowid, servidor, matricula, assunto,
                             processo, corpo_texto)
  VALUES('delete', old.id, old.servidor, old.matricula, old.assunto,
         old.processo, old.corpo_texto);
END;
CREATE TRIGGER IF NOT EXISTS doc_au AFTER UPDATE ON documentos BEGIN
  INSERT INTO documentos_fts(documentos_fts, rowid, servidor, matricula, assunto,
                             processo, corpo_texto)
  VALUES('delete', old.id, old.servidor, old.matricula, old.assunto,
         old.processo, old.corpo_texto);
  INSERT INTO documentos_fts(rowid, servidor, matricula, assunto, processo, corpo_texto)
  VALUES (new.id, new.servidor, new.matricula, new.assunto, new.processo, new.corpo_texto);
END;
"""


def agora() -> str:
    return dt.datetime.now(TZ).isoformat(timespec="seconds")


def _hash(texto: str) -> str:
    return hashlib.sha256((texto or "").encode("utf-8")).hexdigest()[:16]


class Banco:
    """Wrapper fino sobre sqlite3. Uma instancia por processo."""

    def __init__(self, caminho: str | Path):
        self.caminho = str(caminho)
        Path(self.caminho).parent.mkdir(parents=True, exist_ok=True)
        self.tem_fts = False
        self._migrar()

    # ---------------- conexao ----------------

    @contextmanager
    def conn(self):
        c = sqlite3.connect(self.caminho, timeout=30, check_same_thread=False)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()

    def _migrar(self) -> None:
        with self.conn() as c:
            c.executescript(SCHEMA)
            try:
                c.executescript(SCHEMA_FTS)
                self.tem_fts = True
            except sqlite3.OperationalError:
                self.tem_fts = False

    # ---------------- config ----------------

    def set_config(self, chave: str, valor) -> None:
        with self.conn() as c:
            c.execute("INSERT INTO config(chave, valor) VALUES(?,?) "
                      "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",
                      (chave, json.dumps(valor, ensure_ascii=False)))

    def get_config(self, chave: str, padrao=None):
        with self.conn() as c:
            r = c.execute("SELECT valor FROM config WHERE chave=?", (chave,)).fetchone()
        if not r:
            return padrao
        try:
            return json.loads(r["valor"])
        except json.JSONDecodeError:
            return padrao

    # ---------------- documentos ----------------

    def salvar_documento(self, dados: dict) -> int:
        """Cria o documento e a versao 1."""
        ts = agora()
        corpo_html = dados.get("corpo_html", "")
        corpo_txt = dados.get("corpo_texto", "")
        h = _hash(corpo_txt or corpo_html)
        with self.conn() as c:
            cur = c.execute("""
                INSERT INTO documentos(
                    criado_em, atualizado_em, tipologia, materia, situacao, modelos,
                    servidor, matricula, assunto, processo, cabecalho, rodape,
                    corpo_html, corpo_texto, campos_faltantes, entidades,
                    classificacao, provedores, status, versao_atual, hash,
                    arquivo_nome, drive_id, drive_link, docx_path)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                ts, ts, dados.get("tipologia", "DOCUMENTO"), dados.get("materia"),
                dados.get("situacao"), json.dumps(dados.get("modelos", []),
                                                  ensure_ascii=False),
                dados.get("servidor"), dados.get("matricula"), dados.get("assunto"),
                dados.get("processo"), dados.get("cabecalho", ""),
                dados.get("rodape", ""), corpo_html, corpo_txt,
                json.dumps(dados.get("campos_faltantes", []), ensure_ascii=False),
                json.dumps(dados.get("entidades", {}), ensure_ascii=False),
                json.dumps(dados.get("classificacao", {}), ensure_ascii=False),
                json.dumps(dados.get("provedores", []), ensure_ascii=False),
                dados.get("status", "rascunho"), 1, h,
                dados.get("arquivo_nome"), dados.get("drive_id"),
                dados.get("drive_link"), dados.get("docx_path")))
            doc_id = cur.lastrowid
            c.execute("""INSERT INTO versoes(documento_id, versao, criado_em,
                         corpo_html, corpo_texto, cabecalho, rodape, nota, hash)
                         VALUES(?,?,?,?,?,?,?,?,?)""",
                      (doc_id, 1, ts, corpo_html, corpo_txt,
                       dados.get("cabecalho", ""), dados.get("rodape", ""),
                       "versao inicial gerada pelo pipeline", h))
        if dados.get("matricula"):
            self.upsert_servidor(dados.get("matricula"), dados.get("servidor"),
                                 dados.get("cargo"), dados.get("unidade"))
        return doc_id

    def atualizar_documento(self, doc_id: int, corpo_html: str, corpo_texto: str,
                            cabecalho: str = "", rodape: str = "",
                            nota: str = "edicao manual", **campos) -> int:
        """Grava nova versao e atualiza o ponteiro. Retorna o numero da nova versao."""
        ts = agora()
        h = _hash(corpo_texto or corpo_html)
        with self.conn() as c:
            r = c.execute("SELECT versao_atual FROM documentos WHERE id=?",
                          (doc_id,)).fetchone()
            if not r:
                raise ValueError(f"documento {doc_id} inexistente")
            nova = int(r["versao_atual"]) + 1
            c.execute("""INSERT INTO versoes(documento_id, versao, criado_em,
                         corpo_html, corpo_texto, cabecalho, rodape, nota, hash)
                         VALUES(?,?,?,?,?,?,?,?,?)""",
                      (doc_id, nova, ts, corpo_html, corpo_texto,
                       cabecalho, rodape, nota, h))
            sets = ["atualizado_em=?", "corpo_html=?", "corpo_texto=?",
                    "cabecalho=?", "rodape=?", "versao_atual=?", "hash=?"]
            vals = [ts, corpo_html, corpo_texto, cabecalho, rodape, nova, h]
            for k, v in campos.items():
                if k in ("status", "assunto", "processo", "servidor", "matricula",
                         "arquivo_nome", "drive_id", "drive_link", "docx_path",
                         "tipologia"):
                    sets.append(f"{k}=?")
                    vals.append(v)
            vals.append(doc_id)
            c.execute(f"UPDATE documentos SET {', '.join(sets)} WHERE id=?", vals)
        return nova

    def documento(self, doc_id: int) -> dict | None:
        with self.conn() as c:
            r = c.execute("SELECT * FROM documentos WHERE id=?", (doc_id,)).fetchone()
        return dict(r) if r else None

    def listar_documentos(self, busca: str = "", matricula: str = "",
                          tipologia: str = "", status: str = "",
                          limite: int = 300) -> list[dict]:
        clausulas, params = [], []
        if matricula:
            clausulas.append("matricula = ?")
            params.append(matricula)
        if tipologia:
            clausulas.append("tipologia = ?")
            params.append(tipologia)
        if status:
            clausulas.append("status = ?")
            params.append(status)
        if busca:
            like = f"%{busca}%"
            clausulas.append("(servidor LIKE ? OR matricula LIKE ? OR assunto LIKE ? "
                             "OR processo LIKE ? OR corpo_texto LIKE ?)")
            params += [like] * 5
        onde = ("WHERE " + " AND ".join(clausulas)) if clausulas else ""
        with self.conn() as c:
            rows = c.execute(
                f"""SELECT id, criado_em, atualizado_em, tipologia, materia, servidor,
                           matricula, assunto, processo, status, versao_atual,
                           arquivo_nome, drive_link, docx_path, campos_faltantes
                    FROM documentos {onde}
                    ORDER BY atualizado_em DESC LIMIT ?""",
                params + [limite]).fetchall()
        return [dict(r) for r in rows]

    def versoes(self, doc_id: int) -> list[dict]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT id, versao, criado_em, nota, hash, length(corpo_texto) AS tam "
                "FROM versoes WHERE documento_id=? ORDER BY versao DESC",
                (doc_id,)).fetchall()
        return [dict(r) for r in rows]

    def versao(self, doc_id: int, versao: int) -> dict | None:
        with self.conn() as c:
            r = c.execute("SELECT * FROM versoes WHERE documento_id=? AND versao=?",
                          (doc_id, versao)).fetchone()
        return dict(r) if r else None

    def excluir_documento(self, doc_id: int) -> None:
        with self.conn() as c:
            c.execute("DELETE FROM documentos WHERE id=?", (doc_id,))

    # ---------------- anexos ----------------

    def salvar_anexos(self, doc_id: int, extracoes) -> None:
        ts = agora()
        with self.conn() as c:
            for e in extracoes:
                c.execute("""INSERT INTO anexos(documento_id, criado_em, nome, origem,
                             paginas, markdown, erro) VALUES(?,?,?,?,?,?,?)""",
                          (doc_id, ts, e.nome, e.origem, e.paginas,
                           e.markdown[:400000], e.erro))

    def anexos(self, doc_id: int) -> list[dict]:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM anexos WHERE documento_id=? ORDER BY id",
                             (doc_id,)).fetchall()
        return [dict(r) for r in rows]

    # ---------------- base de conhecimento ----------------

    def upsert_kb(self, identificador: str, caminho: str, base: str,
                  conteudo_md: str, frontmatter: dict, origem: str = "manual",
                  arquivo_fonte: str = "") -> int:
        ts = agora()
        h = _hash(conteudo_md)
        with self.conn() as c:
            cur = c.execute("""
                INSERT INTO kb_arquivos(criado_em, atualizado_em, identificador,
                    caminho, base, tipologia, materia, situacao, origem,
                    arquivo_fonte, conteudo_md, frontmatter, ativo, hash)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1,?)
                ON CONFLICT(caminho) DO UPDATE SET
                    atualizado_em=excluded.atualizado_em,
                    identificador=excluded.identificador,
                    tipologia=excluded.tipologia, materia=excluded.materia,
                    situacao=excluded.situacao, conteudo_md=excluded.conteudo_md,
                    frontmatter=excluded.frontmatter, hash=excluded.hash""",
                (ts, ts, identificador, caminho, base,
                 frontmatter.get("tipologia", ""),
                 frontmatter.get("materia") or frontmatter.get("evento", ""),
                 frontmatter.get("situacao", ""), origem, arquivo_fonte,
                 conteudo_md, json.dumps(frontmatter, ensure_ascii=False), h))
            return cur.lastrowid

    def listar_kb(self, apenas_ativos: bool = True) -> list[dict]:
        with self.conn() as c:
            q = ("SELECT id, identificador, caminho, base, tipologia, materia, "
                 "situacao, origem, arquivo_fonte, ativo, atualizado_em, "
                 "length(conteudo_md) AS tam FROM kb_arquivos")
            if apenas_ativos:
                q += " WHERE ativo=1"
            q += " ORDER BY base, identificador"
            return [dict(r) for r in c.execute(q).fetchall()]

    def kb_conteudo(self, kb_id: int) -> dict | None:
        with self.conn() as c:
            r = c.execute("SELECT * FROM kb_arquivos WHERE id=?", (kb_id,)).fetchone()
        return dict(r) if r else None

    def alternar_kb(self, kb_id: int, ativo: bool) -> None:
        with self.conn() as c:
            c.execute("UPDATE kb_arquivos SET ativo=?, atualizado_em=? WHERE id=?",
                      (1 if ativo else 0, agora(), kb_id))

    def excluir_kb(self, kb_id: int) -> None:
        with self.conn() as c:
            c.execute("DELETE FROM kb_arquivos WHERE id=?", (kb_id,))

    def sincronizar_kb_do_disco(self, kb_dir: str | Path) -> int:
        """Internaliza no banco todos os .md da pasta kb/. Idempotente."""
        from . import kb as kbmod
        docs = kbmod.carregar(kb_dir)
        for d in docs:
            self.upsert_kb(d.id, d.caminho, d.base, d.texto, d.meta, origem="manual")
        return len(docs)

    def exportar_kb_para_disco(self, kb_dir: str | Path) -> int:
        """Escreve de volta em kb/ os .md ativos — util para versionar no GitHub."""
        kb_dir = Path(kb_dir)
        n = 0
        for reg in self.listar_kb(apenas_ativos=True):
            conteudo = self.kb_conteudo(reg["id"])["conteudo_md"]
            destino = kb_dir / reg["caminho"]
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(conteudo, encoding="utf-8")
            n += 1
        return n

    # ---------------- servidores ----------------

    def upsert_servidor(self, matricula: str, nome: str = "", cargo: str = "",
                        unidade: str = "") -> None:
        if not matricula:
            return
        with self.conn() as c:
            c.execute("""INSERT INTO servidores(matricula, nome, cargo, unidade,
                         atualizado_em) VALUES(?,?,?,?,?)
                         ON CONFLICT(matricula) DO UPDATE SET
                           nome=COALESCE(NULLIF(excluded.nome,''), servidores.nome),
                           cargo=COALESCE(NULLIF(excluded.cargo,''), servidores.cargo),
                           unidade=COALESCE(NULLIF(excluded.unidade,''), servidores.unidade),
                           atualizado_em=excluded.atualizado_em""",
                      (str(matricula), nome or "", cargo or "", unidade or "", agora()))

    def historico_servidor(self, matricula: str) -> list[dict]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT id, criado_em, tipologia, materia, assunto, processo, status "
                "FROM documentos WHERE matricula=? ORDER BY criado_em",
                (str(matricula),)).fetchall()
        return [dict(r) for r in rows]

    # ---------------- eventos ----------------

    def log(self, etapa: str, detalhe: str = "", provedor: str = "",
            documento_id: int | None = None, duracao: float = 0.0,
            nivel: str = "info") -> None:
        with self.conn() as c:
            c.execute("""INSERT INTO eventos(criado_em, documento_id, etapa, provedor,
                         duracao_seg, detalhe, nivel) VALUES(?,?,?,?,?,?,?)""",
                      (agora(), documento_id, etapa, provedor, duracao,
                       detalhe[:4000], nivel))

    def eventos(self, limite: int = 200) -> list[dict]:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM eventos ORDER BY id DESC LIMIT ?",
                             (limite,)).fetchall()
        return [dict(r) for r in rows]

    # ---------------- estatisticas ----------------

    def estatisticas(self) -> dict:
        with self.conn() as c:
            q = lambda s: c.execute(s).fetchone()[0]
            return {
                "documentos": q("SELECT COUNT(*) FROM documentos"),
                "versoes": q("SELECT COUNT(*) FROM versoes"),
                "kb_ativos": q("SELECT COUNT(*) FROM kb_arquivos WHERE ativo=1"),
                "kb_total": q("SELECT COUNT(*) FROM kb_arquivos"),
                "servidores": q("SELECT COUNT(*) FROM servidores"),
                "anexos": q("SELECT COUNT(*) FROM anexos"),
                "expedidos": q("SELECT COUNT(*) FROM documentos WHERE status='expedido'"),
            }


# --------------------------------------------------------------------------- #
# EXPORTACAO PARA GITHUB
# --------------------------------------------------------------------------- #

def exportar_pacote_github(banco: "Banco", destino_zip: str | Path,
                           incluir_documentos: bool = False) -> Path:
    """
    Gera um .zip pronto para commit: todos os .md ativos da base de conhecimento,
    um INDEX.md navegavel e o catalogo.json. Opcionalmente inclui os documentos
    produzidos, ja em .md.
    """
    import zipfile

    destino = Path(destino_zip)
    destino.parent.mkdir(parents=True, exist_ok=True)
    registros = banco.listar_kb(apenas_ativos=True)

    linhas_index = [
        "# BASE DE CONHECIMENTO — COCARREIRA/CAEDNC",
        "",
        f"Exportado em {agora()} · {len(registros)} arquivo(s)",
        "",
        "| ID | Tipologia | Matéria | Situação | Origem | Arquivo |",
        "|---|---|---|---|---|---|",
    ]
    catalogo = []

    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for reg in registros:
            conteudo = banco.kb_conteudo(reg["id"])["conteudo_md"]
            z.writestr(f"kb/{reg['caminho']}", conteudo)
            linhas_index.append(
                f"| {reg['identificador']} | {reg['tipologia'] or '—'} | "
                f"{reg['materia'] or '—'} | {reg['situacao'] or '—'} | "
                f"{reg['origem']} | `{reg['caminho']}` |")
            catalogo.append({
                "id": reg["identificador"], "caminho": reg["caminho"],
                "base": reg["base"], "tipologia": reg["tipologia"],
                "materia": reg["materia"], "situacao": reg["situacao"],
                "origem": reg["origem"], "arquivo_fonte": reg["arquivo_fonte"],
            })

        if incluir_documentos:
            for d in banco.listar_documentos(limite=5000):
                doc = banco.documento(d["id"])
                nome = (doc["arquivo_nome"] or f"documento_{doc['id']}")
                cabecalho = [
                    "---",
                    f"doc_id: {doc['id']}",
                    f"tipologia: {doc['tipologia']}",
                    f"servidor: {doc['servidor'] or ''}",
                    f"matricula: {doc['matricula'] or ''}",
                    f"assunto: {doc['assunto'] or ''}",
                    f"processo: {doc['processo'] or ''}",
                    f"status: {doc['status']}",
                    f"versao: {doc['versao_atual']}",
                    f"criado_em: {doc['criado_em']}",
                    "---", "",
                ]
                z.writestr(f"documentos/{nome}.md",
                           "\n".join(cabecalho) + (doc["corpo_texto"] or ""))

        z.writestr("kb/INDEX.md", "\n".join(linhas_index))
        z.writestr("kb/catalogo.json",
                   json.dumps({"exportado_em": agora(),
                               "total": len(catalogo),
                               "modelos": catalogo},
                              ensure_ascii=False, indent=2))
        z.writestr(".gitignore",
                   "\n".join(["api_keys.json", "service_account.json", "*.db",
                              "*.db-wal", "*.db-shm", "saida/", "__pycache__/",
                              "*.pyc", ".venv/"]) + "\n")
    return destino
