---
id: INDEX-RH-001
base: 01_BASE_RH_AUXILIO_BOLSA
escopo: Assistente de RH / Auxilio-Bolsa / TJMA
versao: 1.0
data_corte: 2026-08-06
---

# INDICE DA BASE 01 — RH / AUXILIO-BOLSA / TJMA

Esta base contem os .md normativos e de modelagem do Auxilio-Bolsa de Estudos
da CAEDNC/TJMA. Um assistente de RH carregado com esta base deve ser capaz de
responder, sem consulta externa:

- Quais modelos de documento existem armazenados.
- Qual tipologia se aplica ao caso narrado pelo usuario.
- Quais campos sao obrigatorios e quais ficam em branco para preenchimento.
- Qual a base legal invocada em cada peca.

## ARQUIVOS

| Arquivo | Tipologia | Uso |
|---|---|---|
| NORMAS_AUXILIO_BOLSA.md | Norma | Resolucao-GP 1/2023, Portaria-GP 1045/2022, editais EDT-GDG |
| ARVORE_DECISAO_AUXILIO_BOLSA.md | Logica | Classificacao do evento em 4 tipos |
| MOD_AB_01_manifestacao_implantacao.md | MANIFESTACAO | 1a concessao |
| MOD_AB_02_oficio_implantacao.md | OFICIO | 1a concessao |
| MOD_AB_03_manifestacao_renovacao_sem_mudanca.md | MANIFESTACAO | Renovacao valor igual |
| MOD_AB_04_oficio_renovacao_sem_mudanca.md | OFICIO | Renovacao valor igual |
| MOD_AB_05_manifestacao_renovacao_aumento.md | MANIFESTACAO | Renovacao com aumento |
| MOD_AB_06_oficio_renovacao_aumento.md | OFICIO | Renovacao com aumento |
| MOD_AB_07_manifestacao_renovacao_reducao.md | MANIFESTACAO | Renovacao com reducao |
| MOD_AB_08_oficio_renovacao_reducao.md | OFICIO | Renovacao com reducao |

## REGRA DE PAREAMENTO
Todo evento de Auxilio-Bolsa gera SEMPRE um PAR: MANIFESTACAO (interna) seguida de
OFICIO (externo, a Coordenadoria de Pagamento), nessa ordem, nunca isoladamente.
