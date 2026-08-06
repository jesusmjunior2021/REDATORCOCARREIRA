---
id: MOD-GEN-01
tipologia: INFORMACAO
materia: Generico (fallback universal)
uso: Quando a materia nao tem modelo catalogado
---

# INFORMACAO — ESQUELETO UNIVERSAL COCARREIRA/CAEDNC

A INFORMACAO da COCARREIRA obedece invariavelmente a esta sequencia de blocos:

| # | Bloco | Funcao | Obrigatorio |
|---|---|---|---|
| 1 | Cabecalho de indexacao | Processo / Assunto / Objeto / Requerente | Recomendado |
| 2 | Titulo | A palavra INFORMACAO isolada, em caixa alta | Sim |
| 3 | Relatorio | "Trata-se de processo em que ..." — quem pede, o que pede, de onde para onde | Sim |
| 4 | Marcador de transicao | "E o breve relatorio. Segue a manifestacao desta Coordenadoria." | Opcional |
| 5 | Preliminar | Esclarecimento de instituto/enquadramento juridico, se houver risco de confusao | Condicional |
| 6 | Instrucao probatoria | Anuencia das chefias, certidao PAD, dossie MentoRH, intersticios | Sim |
| 7 | Fundamentacao | Artigos da RESOL-GP aplicavel, com citacao entre aspas quando transcrita | Sim |
| 8 | Conclusao/Encaminhamento | "Encaminhe-se os autos ao Gabinete da Diretora-Geral para analise e deliberacao." | Sim |
| 9 | Local e data | "Sao Luis, {DATA}." | Recomendado |

```
{NUM_PROCESSO_BLOCO}

INFORMACAO

Trata-se de processo administrativo em que {REQUERENTE} {VERBO_DO_PEDIDO} {OBJETO_DO_PEDIDO}.

E o breve relatorio. Segue a manifestacao desta Coordenadoria.

{BLOCO_PRELIMINAR}

{BLOCO_INSTRUCAO_PROBATORIA}

{BLOCO_FUNDAMENTACAO}

{BLOCO_ENCAMINHAMENTO}

Sao Luis, {DATA}.
```
