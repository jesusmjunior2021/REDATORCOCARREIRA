---
id: LOG-AB-001
base: 01_BASE_RH_AUXILIO_BOLSA
tipo: logica_de_classificacao
---

# ARVORE DE DECISAO — CLASSIFICACAO DO EVENTO DE AUXILIO-BOLSA

## PERGUNTA 1 — E a primeira concessao do beneficio para este servidor neste edital?
- **SIM** -> `TIPO = IMPLANTACAO`
  - Base: art. 8o da RESOL-GP 1/2023 + item 2.2 do edital EDT-GDG + teto da PORT-GP 1045/2022.
  - Pecas: `MOD_AB_01` + `MOD_AB_02`.
- **NAO** -> e RENOVACAO SEMESTRAL (art. 14 da RESOL-GP 1/2023). Ir a Pergunta 2.

## PERGUNTA 2 — Comparar a mensalidade efetivamente paga do semestre novo com a do anterior
- **IGUAL** -> `TIPO = RENOVACAO SEM MUDANCA DE VALOR` -> `MOD_AB_03` + `MOD_AB_04`.
- **MAIOR** -> `TIPO = RENOVACAO COM AUMENTO DE MENSALIDADE` -> `MOD_AB_05` + `MOD_AB_06`.
  Recalcular 70% sobre o novo valor pago (art. 3o, §1o/§2o).
- **MENOR** -> `TIPO = RENOVACAO COM REDUCAO DE MENSALIDADE` -> `MOD_AB_07` + `MOD_AB_08`.
  Recalcular 70% sobre o novo valor pago (art. 3o, §1o/§2o).

## PERGUNTA 3 — Periodo de referencia
- Janeiro a junho -> 1o semestre. Julho a dezembro -> 2o semestre.
- Altera apenas datas e periodo citados, nunca a estrutura do modelo.

## SAIDA OBRIGATORIA AO FINAL DA REDACAO
```
Tipo classificado: <IMPLANTACAO | RENOVACAO SEM MUDANCA DE VALOR |
                    RENOVACAO COM AUMENTO DE MENSALIDADE |
                    RENOVACAO COM REDUCAO DE MENSALIDADE>
Semestre de referencia: <1o | 2o>
```
