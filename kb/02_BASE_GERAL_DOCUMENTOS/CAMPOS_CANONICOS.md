---
id: CAMPOS-001
base: 02_BASE_GERAL_DOCUMENTOS
tipo: dicionario_de_dados
---

# DICIONARIO DE CAMPOS CANONICOS

Todo modelo .md desta base usa exclusivamente os nomes abaixo. A aplicacao Python e o GEM
devem gerar formulario a partir de `campos_obrigatorios` do frontmatter.

## IDENTIFICACAO DO SERVIDOR
| Campo | Tipo | Fonte | Inferivel pela IA? |
|---|---|---|---|
| NOME | texto | Requerimento / MentoRH | NAO |
| MATRICULA | numero | MentoRH | NAO |
| CARGO | texto | MentoRH | NAO |
| UNIDADE_ORIGEM | texto | MentoRH | NAO |
| UNIDADE_DESTINO | texto | Requerimento | NAO |

## IDENTIFICACAO DO PROCESSO
| Campo | Tipo | Fonte | Inferivel? |
|---|---|---|---|
| NUM_PROCESSO | NNNNN/AAAA | DigiDoc | NAO |
| NUM_MANIF | NNNN/AAAA | Numeracao CAEDNC | NAO |
| NUM_INFORMA | NNNNAAAA | Numeracao CAEDNC | NAO |
| COD_VALIDACAO | hex | DigiDoc | NAO |
| ID_MOVIMENTACAO | numero | DigiDoc | NAO |
| NUM_DECISAO | NNNNAAAA | Gabinete | NAO |
| OFC_REFERENCIA | sigla-NNNNAAAA | Autos | NAO |
| DATA / DATA_OFICIO | por extenso | Sistema | SIM (data corrente) |

## AUXILIO-BOLSA
| Campo | Tipo | Regra |
|---|---|---|
| EDITAL | EDT-GDG NNN/AAAA | NAO inferir |
| CURSO, IES, MODALIDADE, PERIODO_CURSO | texto | do contrato/declaracao |
| VLR_CONTRATADO, VLR_PAGO | moeda | do comprovante |
| VLR_70PCT | moeda | **CALCULADO** = VLR_PAGO * 0,70, limitado ao teto |
| VLR_PAGO_ANTERIOR, VLR_PAGO_NOVO | moeda | comparacao semestral |
| VLR_BRUTO_ANTIGO, VLR_BRUTO_NOVO | moeda | valor sem descontos |
| VLR_70PCT_NOVO | moeda | **CALCULADO** sobre VLR_PAGO_NOVO |
| MES_REAJUSTE | mes/ano | do comprovante |
| PERIODO_MESES | "janeiro a junho de AAAA" | derivado do semestre |
| LINHAS_POR_MES | tabela | uma linha por mes comprovado |

## REGRA DE OURO
Campo marcado como **nao inferivel** que nao venha no caso concreto NUNCA e preenchido por
suposicao. Grava-se literalmente:
```
[DADO FALTANTE: <nome do campo>]
```
Na aplicacao Python, esses campos aparecem em branco no formulario, destacados em vermelho.
