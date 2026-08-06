---
id: LOG-GERAL-001
base: 02_BASE_GERAL_DOCUMENTOS
tipo: logica_de_classificacao
---

# ARVORE DE DECISAO — SELECAO DA TIPOLOGIA DOCUMENTAL

## NIVEL 1 — QUAL A MATERIA?
```
Auxilio-Bolsa de Estudos ........................ ir para ARVORE_DECISAO_AUXILIO_BOLSA.md (BASE 01)
Movimentacao funcional .......................... NIVEL 2
Devolucao de servidor ........................... MOD-DEV-01
Reconducao ao cargo ............................. MOD-REC-01
Materia sem modelo catalogado ................... MOD-GEN-01 + marcar [MODELO NAO CATALOGADO]
```

## NIVEL 2 — QUAL O INSTITUTO DE MOVIMENTACAO?
```
P2.1 O pedido altera a LOTACAO DE ORIGEM?
     NAO -> e ALTERACAO DE LOTACAO DE EXERCICIO / DISPOSICAO
            P2.1.1 Quem pede?
                   Servidor ................. MOD-REL-02
                   Gestor, 1 servidor ....... MOD-REL-03
                   Gestor, varios ........... MOD-REL-04
     SIM -> P2.2

P2.2 Ha deslocamento reciproco de dois servidores de municipios diferentes?
     SIM -> PERMUTA -> P2.3
     NAO -> P2.4

P2.3 Certidao PAD ja consta nos autos?
     SIM -> MOD-PER-01
     NAO -> MOD-PER-02

P2.4 O pedido e do proprio servidor para outra comarca/municipio?
     SIM -> REMOCAO A PEDIDO -> MOD-REM-01
     NAO -> RELOTACAO -> P2.5

P2.5 Estado da instrucao:
     Anuencia OK + certidao PAD OK + sem movimentacao 6 meses .. MOD-REL-01
     Requerida por autoridade, requisitos cumpridos ............ MOD-REL-05
     Chefia manifestou-se DESFAVORAVEL ........................ MOD-REL-06
     Falta anuencia (abrir vista) ............................. MOD-REL-07 (DESPACHO)
     Decisao ja proferida, falta portaria ..................... MOD-REL-08 (DESPACHO)
```

## NIVEL 3 — TRAVAS OBRIGATORIAS ANTES DE OPINAR PELO DEFERIMENTO
```
T1  Intersticio de 6 meses (art. 4o, par. unico, RESOL-GP-232010 c/ RESOL-GP-472011)
    -> relotacao, remocao a pedido, permuta.
T2  Intersticio de 2 anos (art. 1o, par. unico, RESOL-GP-432019)
    -> remocao a pedido e permuta.
T3  Certidao negativa de PAD/sindicancia.
T4  Manifestacao expressa das chefias imediatas (§1o, art. 3o).
T5  Impacto no 1o Grau (RESOL-GP-192023 / CNJ 194 e 219).
Qualquer trava nao comprovada nos autos => a peca NAO opina pelo deferimento;
redige-se remessa para diligencia.
```

## NIVEL 4 — PECA COMPLEMENTAR
```
Comunicacao externa a outro orgao/coordenadoria ....... MOD-GEN-03 (OFICIO)
Comunicacao interna / resposta DigiDoc ................ MOD-GEN-04 (MEMORANDO)
Peticionamento do proprio servidor .................... MOD-GEN-05 (REQUERIMENTO)
```
