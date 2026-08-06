---
id: NORM-AB-001
base: 01_BASE_RH_AUXILIO_BOLSA
tipo: norma
palavras_chave: [auxilio-bolsa, resolucao-gp 1/2023, portaria-gp 1045/2022, CAEDNC, TJMA, 70%]
---

# NORMAS DO AUXILIO-BOLSA DE ESTUDOS — CAEDNC/TJMA

## RESOLUCAO-GP N.o 1/2023
- **art. 3o** — o beneficio corresponde a **70% do valor efetivamente pago** pelo
  servidor a instituicao de ensino.
  - **§1o / §2o** — havendo alteracao do valor efetivamente pago (aumento ou reducao),
    o beneficio deve ser **recalculado** sobre o novo valor pago.
- **art. 8o** — criterios de elegibilidade para a concessao.
- **art. 14** — documentacao comprobatoria exigida para a **renovacao semestral**.
  O nao envio ou a nao manifestacao implica **suspensao do beneficio**.

## PORTARIA-GP N.o 1045/2022
- Fixa o **teto** do valor do auxilio. O valor calculado a 70% nunca pode
  ultrapassar o teto vigente.

## EDITAIS EDT-GDG
- **item 2.2** — requisitos do edital de convocacao. O numero/ano do edital e dado
  obrigatorio e deve vir do caso concreto; nunca inventar.

## FORMULA CANONICA
```
VLR_70PCT = ARREDONDA(VLR_PAGO * 0,70 ; 2)
SE VLR_70PCT > TETO_PORTARIA_1045_2022 ENTAO VLR_70PCT = TETO
```
O valor calculado deve SEMPRE aparecer resolvido na peca. Nunca deixar formula.

## PERIODO DE REFERENCIA
- Janeiro a junho -> 1o semestre.
- Julho a dezembro -> 2o semestre.

## DESTINATARIO PADRAO DO OFICIO
Coordenadoria de Pagamento — a titular vigente deve ser confirmada no caso concreto;
o modelo historico registra KENIA CIANA ARAUJO SILVA, Coordenadora de Pagamento.
