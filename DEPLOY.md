# DEPLOY — Streamlit Cloud e local

## ESTRUTURA OBRIGATORIA DO REPOSITORIO

O Streamlit Cloud executa `app.py` a partir da **raiz** do repositorio. A pasta
`core/` precisa estar **ao lado** do `app.py`, nao dentro de uma subpasta.

### Correto
```
seu-repositorio/
├── app.py
├── cli.py
├── requirements.txt
├── schema.yml
├── .gitignore
├── .streamlit/
│   └── config.toml
├── core/
│   ├── __init__.py
│   ├── db.py
│   ├── editor.py
│   ├── exporters.py
│   ├── gaps.py
│   ├── ingest.py
│   ├── kb.py
│   ├── keys.py
│   ├── llm.py
│   ├── parsing.py
│   ├── pipeline.py
│   └── sheets.py
├── kb/
│   ├── 01_BASE_RH_AUXILIO_BOLSA/
│   └── 02_BASE_GERAL_DOCUMENTOS/
└── GEM_REDATOR_PROMPT.md
```

### Errado — causa `ImportError` na linha do `from core import ...`
```
seu-repositorio/
└── REDATOR_COCARREIRA/     <- app.py aqui dentro, mas o Cloud roda da raiz
    ├── app.py
    └── core/
```

Se o seu repositorio estiver assim, mova o conteudo para a raiz:
```bash
git mv REDATOR_COCARREIRA/* .
git mv REDATOR_COCARREIRA/.gitignore .
rmdir REDATOR_COCARREIRA
git commit -m "move conteudo para a raiz do repositorio"
git push
```

Alternativa sem mover nada: em **Manage app → Settings → Main file path**,
informe `REDATOR_COCARREIRA/app.py`.

## VERIFICACAO ANTES DO PUSH

```bash
python -c "import ast,pathlib; [ast.parse(p.read_text()) for p in pathlib.Path('.').rglob('*.py')]; print('sintaxe ok')"
ls core/__init__.py            # precisa existir
git ls-files core/ | wc -l     # precisa listar 12 arquivos
```

O `core/__init__.py` e o erro mais comum: se ele nao estiver **versionado**, o
import quebra. Confira com `git ls-files core/__init__.py` — se nao aparecer,
force com `git add -f core/__init__.py`.

## DIAGNOSTICO EMBUTIDO

O `app.py` agora captura falhas de import e exibe uma pagina com:
- o nome exato do modulo que faltou;
- a versao do Python e o `sys.path`;
- a listagem do diretorio do app e da pasta `core/`;
- o traceback completo.

Isso substitui a mensagem censurada do Streamlit Cloud.

## SECRETS (nao commitar chaves)

Em **Manage app → Settings → Secrets**, cole:

```toml
[api]
llamaparse = "llx-..."
groq = "gsk_..."
cerebras = "csk-..."

[google]
service_account = '''
{ "type": "service_account", "project_id": "...", ... }
'''
```

Depois cadastre as chaves pela aba **Sistema** ou importe o `api_keys.json`.

## PERSISTENCIA NO STREAMLIT CLOUD

O disco do Cloud e **efemero**: `redator.db` e `saida/` se perdem a cada reboot.
Para producao:
- use a rota do **Google Drive** (Docs + planilha) como armazenamento duravel;
- baixe periodicamente o `redator.db` pela aba Sistema;
- ou aponte o SQLite para um volume persistente, rodando local ou em VPS.

Local, com persistencia real:
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```
