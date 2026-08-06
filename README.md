# REDATOR COCARREIRA/CAEDNC — TJMA
Aplicacao Python de redacao de documentos oficiais.
Autor: Adm. Jesus Martins · v3.1 · 2026-08-06

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
app.py                      Interface Streamlit — 5 abas
cli.py                      Execucao headless / lote
schema.yml                  Contrato estrutural (SQLite + .md + pipeline)
redator.db                  SQLite3 — criado na primeira execucao
requirements.txt
GEM_REDATOR_PROMPT.md       Prompt-mestre usado como system prompt na etapa [4]
core/
  keys.py                   Pool de chaves, rodizio, cooldown, import/export JSON
  parsing.py                LlamaParse + fallbacks locais
  llm.py                    Cliente unico Groq/Cerebras/Grok/Gemini com rodizio
  kb.py                     Carga dos .md, busca fuzzy, montagem de contexto
  pipeline.py               Orquestracao das etapas 1 a 4
  editor.py                 HTML <-> texto <-> docx, CSS da folha A4
  db.py                     Persistencia SQLite3 com versionamento
  ingest.py                 PDF -> LlamaParse -> .md -> banco
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

## NOVIDADES DA v3.1 — EXTRACAO DIRIGIDA AS LACUNAS

### O fluxo real de preenchimento
Antes o LlamaParse lia os anexos "no geral". Agora, **assim que o operador escolhe o
modelo** (ofício, memorando, informação...), o app:

1. Lê os `campos_obrigatorios` daquele `.md` e transforma em **CAMPOS-ALVO**.
2. Mostra um formulário com todos eles — o operador preenche só o que já sabe.
3. Monta uma `parsing_instruction` **dirigida**, listando cada campo-alvo e o que
   procurar. Isso muda o comportamento do LlamaParse: em vez de resumir, ele
   preserva as regiões onde esses dados costumam estar (tabelas de mensalidade,
   cabeçalho de matrícula, rodapé de portaria).
4. Faz uma **segunda passagem** por documento, caçando cada alvo e devolvendo
   `valor` · `página` · `trecho` · `confiança`.
5. Consolida: maior confiança vence; o que o operador digitou tem precedência.

Regra do extrator, inegociável: *nunca deduza, nunca calcule, nunca complete com
conhecimento externo — copie o que está escrito.*

### Percentual de completude
- **Por documento** — quantos alvos aquele anexo sozinho supriu.
- **Geral** — quantos alvos foram supridos por qualquer anexo.
Semáforo: 🟢 ≥80% · 🟡 ≥50% · 🔴 <50%.

O painel tem três abas: **Localizados** (com fonte, página e trecho para auditoria),
**Lacunas** (com a dica do que procurar em cada campo) e **Evidências .md**.

### Artefatos .md
Cada anexo vira um `.md` enxuto de evidências, e o conjunto vira um `DOSSIE.md`.
É esse formato que vai para o redator — processa muito melhor que o PDF bruto — e é
o que você commita no GitHub. Botão grava tudo em `saida/evidencias/`.

### Editor: salvar, avançar, apagar
| Botão | Efeito |
|---|---|
| 💾 Salvar | grava no SQLite; se já existe, cria **nova versão** |
| ⏩ Avançar status | rascunho → revisado → expedido, versionando |
| 🧹 Apagar texto | limpa o corpo (o conteúdo segue recuperável nas versões) |
| ↩ Recarregar | volta à última versão salva |
| ＋ Inserir lacunas | injeta os `[DADO FALTANTE]` pendentes com a dica de cada um |

### Planilha-banco no Drive
Se não existir planilha, aparece **➕ Criar planilha no Drive**. Ela nasce dentro da
pasta-raiz, em pt_BR, com três abas já formatadas:

| Aba | Alimentação |
|---|---|
| **Documentos** | uma linha por peça enviada, com completude e link do Drive |
| **Servidores** | reescrita do SQLite, com contagem e última movimentação |
| **Lacunas** | uma linha por campo faltante, com a dica de onde buscar |

`garantir()` não duplica planilha existente, e `garantir_abas()` cria abas ausentes
numa planilha que você já tinha. A planilha também é **legível de volta** pelo app —
funciona como banco consultável no próprio Workspace.

### Pacote para o GitHub
Aba **Base de conhecimento** → **📦 Gerar pacote .zip**. Sai com todos os `.md`
ativos, um `INDEX.md` navegável, `catalogo.json` e um `.gitignore` que já protege
`api_keys.json`, `service_account.json`, `*.db` e `saida/`. Opcionalmente inclui os
documentos produzidos, cada um com frontmatter.

## NOVIDADES DA v3.0

### Botao de iniciar
A redacao so comeca quando o operador clica em **▶ INICIAR PROCESSAMENTO**. O botao
fica desabilitado enquanto nao houver chave de inferencia ou entrada (relato/anexo).
Durante a execucao aparece barra de progresso com o cronometro e a etapa corrente.

### Editor tipo Word
Aba **Editor**. Bibliotecas usadas — ambas ja consagradas para este fim em Python:

| Biblioteca | Papel |
|---|---|
| `streamlit-quill` | editor WYSIWYG (Quill.js) com toolbar completa |
| `python-docx` | conversao HTML -> .docx preservando a formatacao |

Recursos: **negrito**, *italico*, sublinhado, tachado, alinhamento (esquerda, centro,
direita, justificado), recuo (+/- 1,25 cm), listas ordenadas e com marcadores,
titulos, cor e realce, citacao e tabelas.

A folha e renderizada em A4 real (21 cm, margens 3/2/3/2 cm, Times 12, entrelinhas 1,5),
com aba **Pre-visualizar folha** que mostra o documento como sairá impresso. Campos
`[DADO FALTANTE: X]` aparecem realcados em amarelo.

**Cabecalho e rodape** sao editaveis em HTML e vao para a secao header/footer do .docx.

### SQLite3
Banco `redator.db`, criado na primeira execucao. Sete tabelas — ver `schema.yml`.

Pontos de projeto:
- **Nenhuma escrita destrutiva.** Salvar de novo cria uma **nova versao** e move o
  ponteiro `versao_atual`. Toda versao anterior continua recuperavel e pode ser
  carregada de volta no editor.
- **Busca full-text** via FTS5 (degrada para LIKE se o SQLite nao tiver FTS5).
- O material bruto extraido pelo LlamaParse fica gravado na tabela `anexos`,
  vinculado ao documento — a procedencia de cada dado permanece auditavel.
- A base de conhecimento inteira tambem vive no banco (`kb_arquivos`), podendo ser
  exportada de volta para `kb/` para versionar no GitHub.

### Galeria
Aba **Galeria**. Lista tudo que foi salvo, com busca por servidor, matricula, assunto,
processo ou conteudo, e filtros por tipologia e status. Ao selecionar, o documento e
renderizado na folha A4; da para reabrir no editor, gerar .docx, abrir no Drive,
inspecionar versoes/anexos/metadados ou excluir.

### Ingestao da base
Aba **Base de conhecimento**. Sobe um PDF -> LlamaParse converte para Markdown -> um
modelo gera o frontmatter canonico (id, tipologia, materia, campos, palavras-chave,
normas citadas) -> o arquivo entra no SQLite **e** em `kb/` como `.md`. Modelos podem
ser ativados/desativados sem apagar. Dois botoes de sincronizacao:
`kb/ → banco` e `banco → kb/` (este ultimo para commitar no GitHub).

### Duas rotas de salvamento
1. **SQLite3** — sempre, com versionamento.
2. **Google Drive** — Google Docs na pasta `{MATRICULA} - {NOME}`, mais linha na
   planilha. O link do Drive volta gravado no registro do banco.

Alem dessas, `.docx` para download e `.md` para o GitHub.

### schema.yml
Contrato estrutural completo: tabelas e colunas do SQLite, frontmatter dos `.md`,
dominios, campos canonicos, travas juridicas, config do editor, provedores, Google
Workspace, arvore de arquivos e os 8 invariantes. Serve para reimplementar a mesma
estrutura em outra stack ou alimentar um GEM/GPT/Claude com o formato esperado.
Baixavel pela aba Sistema.

## ABAS

| Aba | Funcao |
|---|---|
| **Redigir** | relato + anexos + botao de iniciar; trilha, entidades e anexos lidos |
| **Editor** | folha A4, WYSIWYG, cabecalho/rodape, salvar, versoes, docx, Drive |
| **Galeria** | tudo do SQLite, com busca, filtros, reabertura e exclusao |
| **Base de conhecimento** | ingestao de PDF, ativar/desativar, sincronizacao |
| **Sistema** | chaves, rodizio, estatisticas, download do .db e do schema.yml |

## PONTOS DE ATENCAO

- Endpoints e nomes de modelo mudam com frequencia. Conferir `PROVIDERS` em
  `core/keys.py` contra a documentacao vigente de cada API antes de produzir.
- O teto do auxilio-bolsa (PORT-GP 1045/2022) esta na base como trava da formula,
  sem o valor numerico — informar para fechar a lacuna.
