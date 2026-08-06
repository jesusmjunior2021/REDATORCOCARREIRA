---
id: MOD-REM-01
tipologia: INFORMACAO
materia: Remocao a pedido
origem_drive: REMOCAO A PEDIDO/ (INFORMACAO.odt, REMOCAO POR MOTIVO DE SAUDE.odt, Despacho.odt, DESPACHO PARA ANUENCIA DA CHEFIA IMEDIATA.odt)
campos_obrigatorios: [NUM_PROCESSO, NOME, MATRICULA, CARGO, UNIDADE_ORIGEM, UNIDADE_DESTINO, FUNDAMENTO, DATA]
---

# INFORMACAO — REMOCAO A PEDIDO

```
Processo: {NUM_PROCESSO}
Assunto: Remocao a pedido
Requerente: {NOME}

INFORMACAO

Trata-se de processo em que o(a) servidor(a) {NOME}, matricula {MATRICULA}, {CARGO},
lotado(a) {UNIDADE_ORIGEM}, requer remocao para {UNIDADE_DESTINO}, com fundamento em
{FUNDAMENTO}.

Preliminarmente, informamos que {SITUACAO_ANUENCIA_E_CERTIDAO}.

No que se refere ao direito de movimentacao funcional, em atencao ao paragrafo unico do
art. 1o da RESOL-GP-432019, esta Coordenadoria informa que, em consulta aos relatorios do
Sistema MentoRH, no assentamento funcional do(a) referido(a) servidor(a), nao constam
registros de remocao a pedido ou participacao em permuta em prazo inferior a dois anos
(dossie anexo).

{BLOCO_ESPECIFICO}

Encaminhe-se os autos ao Gabinete da Diretora-Geral para analise e deliberacao.

Sao Luis, {DATA}.
```

## VARIANTE — REMOCAO POR MOTIVO DE SAUDE
Substituir `{BLOCO_ESPECIFICO}` por bloco que registre:
- a documentacao medica juntada e o parecer da unidade de saude do Tribunal;
- que a remocao por motivo de saude nao se sujeita ao interstício do art. 1o, paragrafo unico
  da RESOL-GP-432019 quando fundada em laudo, cabendo a Administracao deliberar;
- se ha vaga na unidade de destino.
Se o laudo ou o parecer nao constarem dos autos, redigir remessa para diligencia em vez de
opinar pelo deferimento.

## DESPACHOS AUXILIARES DESTA MATERIA
- Vista a chefia imediata para anuencia -> usar `MOD-REL-07`.
- Cumprimento de decisao / expedicao de portaria -> usar `MOD-REL-08`.
