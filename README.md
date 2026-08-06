# REDATOR COCARREIRA/CAEDNC — TJMA
Aplicacao Python de redacao de documentos oficiais.
Autor: Adm. Jesus Martins · v2.0 · 2026-08-06

## ARQUITETURA DO PIPELINE

```
  ANEXOS (PDF escaneado, dossie MentoRH, certidao, contrato, processo)
      │
      ▼
 [1] LlamaParse ................ extracao fiel -> Markdown  (core/parsing.py)
      │                          fallback local: pdfplumber / python-docx / odt
      ▼
 [2] Groq | Cerebras | Grok .... entidades estruturadas (JSON)  (core/pipeline.py)
      │                          nomes, matriculas, unidades, portarias,
      │                          estado da instrucao, valores de mensalidade
      ▼
 [3] Groq | Cerebras | Grok .... classificacao da tipologia  (core/kb.py + pipeline)
      │                          pre-selecao fuzzy + arvore de decisao dos .md
      │                          + verificacao das travas (intersticios, PAD, anuencia)
      ▼
 [4] Python + modelos .md ...... montagem e redacao da peca final
      │                          resolve pares, campos, calculos de 70%
      ▼
 [5] Saida ..................... .docx | Google Docs | planilha | historico | perfil
```

**Sem estrutura rigida.** Nao ha formulario obrigatorio. O operador descreve o caso
em linguagem natural, anexa o que tiver, e o pipeline decide o resto. O formulario
de identificacao aparece *depois* da redacao, ja pre-preenchido com o que foi
extraido, apenas para nomear o arquivo.

## INSTALACAO

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## ESTRUTURA

```
app.py                      Interface de chat (Streamlit)
cli.py                      Execucao headless / lote
requirements.txt
GEM_REDATOR_PROMPT.md       Prompt-mestre usado como system prompt na etapa [4]
core/
  keys.py                   Pool de chaves, rodizio, cooldown, import/export JSON
  parsing.py                LlamaParse + fallbacks locais
  llm.py                    Cliente unico Groq/Cerebras/Grok/Gemini com rodizio
  kb.py                     Carga dos .md, busca fuzzy, montagem de contexto
  pipeline.py               Orquestracao das etapas 1 a 4
  exporters.py              .docx, Google Docs, Sheets, historico, perfil
kb/
  01_BASE_RH_AUXILIO_BOLSA/   11 arquivos — normas + 8 modelos pareados
  02_BASE_GERAL_DOCUMENTOS/   23 arquivos — 18 modelos + normas + arvores + regras
saida/                      .docx gerados
perfis/                     PERFIL_{MATRICULA}.md consolidados
api_keys.json               gerado automaticamente
historico_documentos.json   gerado automaticamente
```

## CHAVES DE API

Barra lateral -> **Chaves de API**. Provedores:

| Provedor | Papel | Endpoint de validacao |
|---|---|---|
| `llamaparse` | parsing | LlamaCloud `/parsing/supported_file_extensions` |
| `groq` | inferencia | `/openai/v1/models` |
| `cerebras` | inferencia | `/v1/models` |
| `xai` (Grok) | inferencia | `/v1/models` |
| `gemini` | inferencia | camada compativel OpenAI do AI Studio |

A chave so entra no pool se o endpoint responder HTTP 200.

### Rodizio
- Ordem de prioridade dos provedores configuravel na barra lateral.
- Dentro do provedor: chave ativa de **menor contador de uso** (round-robin balanceado).
- HTTP 429/402 -> **cooldown de 15 min**, salta para a proxima chave.
- HTTP 401/403 -> chave marcada `invalida`, sai do rodizio.
- Provedor esgotado -> salta para o proximo da ordem.
- Enquanto houver uma chave viva em qualquer provedor, nao falta API.

### Import/export
`Exportar JSON` baixa o pool inteiro. `Importar JSON` mescla sem duplicar.
Tambem por CLI: `python cli.py --chave groq:gsk_xxx --chave llamaparse:llx_xxx`

## LLAMAPARSE

`core/parsing.py` envia uma **instrucao em linguagem natural** junto do arquivo,
editavel na barra lateral. A instrucao padrao manda preservar nomes, matriculas,
numeros de processo/portaria/resolucao, cargos, unidades, datas e valores, converter
tabelas em Markdown e **nao resumir nem interpretar**.

Sem chave LlamaParse, o fallback local le PDF com camada de texto, DOCX e ODT.
PDF escaneado exige LlamaParse (o app avisa na barra lateral).

## GOOGLE SERVICE ACCOUNT

1. Criar Service Account no Google Cloud; habilitar **Drive API** e **Sheets API**.
2. Baixar o JSON e apontar o caminho na barra lateral.
3. Compartilhar a pasta-raiz do Drive e a planilha com o e-mail da Service Account
   (permissao Editor).
4. Informar o ID da pasta-raiz e o ID da planilha.

### O que grava
- Pasta `{MATRICULA} - {NOME COMPLETO}` (cria se nao existir).
- Google Docs `{MATRICULA}_{NOME}_{ASSUNTO}_{TIPOLOGIA}_{AAAA-MM-DD}` — nomenclatura
  desenhada para busca semantica por matricula, nome ou assunto.
- Linha na aba `Documentos` da planilha (cabecalho criado automaticamente).
- `historico_documentos.json` local.
- `perfis/PERFIL_{MATRICULA}.md` a cada 10 documentos do mesmo servidor, com a
  tabela de movimentacoes e o alerta de intersticio (6 meses / 2 anos).

## CLI

```bash
python cli.py --catalogo
python cli.py --relato "servidor pediu relotacao, chefia concordou" \
              --anexo dossie.pdf --anexo certidao.pdf \
              --nome "FULANO DE TAL" --matricula 102350 \
              --assunto "Relotacao" --docx --json
```

## TRAVAS DE SEGURANCA JURIDICA

A etapa [3] devolve `opinar_pelo_deferimento`. Se qualquer trava estiver violada ou
pendente, o valor vira `false` e a etapa [4] **nao opina pelo deferimento** — redige
remessa para diligencia. Travas verificadas:

| Trava | Norma |
|---|---|
| Intersticio de 6 meses | art. 4o, par. unico, RESOL-GP-232010 c/ RESOL-GP-472011 |
| Intersticio de 2 anos | art. 1o, par. unico, RESOL-GP-432019 |
| Certidao negativa de PAD | Coordenadoria de PAD e Sindicancia |
| Anuencia das chefias | § 1o do art. 3o, RESOL-GP-232010 |
| Impacto no 1o Grau | RESOL-GP-192023 / CNJ 194 e 219 |

Campo nao localizado vira literalmente `[DADO FALTANTE: <campo>]` e aparece
destacado na aba **Trilha do pipeline**. Nada e inventado.

## ABAS DA INTERFACE

- **Redigir** — chat, anexos, trilha do pipeline, entidades extraidas, texto dos
  anexos lidos, edicao do documento antes de salvar.
- **Catalogo de modelos** — 26 modelos, com busca fuzzy por intencao e inspecao do
  `.md` bruto.
- **Historico** — documentos ja gerados, exportavel em JSON.

## PONTOS DE ATENCAO

- Endpoints e nomes de modelo mudam com frequencia. Conferir `PROVIDERS` em
  `core/keys.py` contra a documentacao vigente de cada API antes de produzir.
- O teto do auxilio-bolsa (PORT-GP 1045/2022) esta na base como trava da formula,
  sem o valor numerico — informar para fechar a lacuna.
