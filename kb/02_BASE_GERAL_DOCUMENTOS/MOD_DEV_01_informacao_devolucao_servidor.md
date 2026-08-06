---
id: MOD-DEV-01
tipologia: INFORMACAO
materia: Devolucao de servidor
origem_drive: DEVOLUCAO DE SERVIDOR/Informacao.docx e Informacao 492332022.docx
campos_obrigatorios: [NUM_PROCESSO, AUTORIDADE, NOME, MATRICULA, CARGO, MOTIVO, OFC_REFERENCIA, HISTORICO_MOVIMENTACOES]
---

# INFORMACAO — DEVOLUCAO DE SERVIDOR

```
Processo: {NUM_PROCESSO}
Assunto: Devolucao de Servidor {NOME}

INFORMACAO

Trata-se de processo administrativo em que {AUTORIDADE} devolve o(a) servidor(a) {NOME},
matricula {MATRICULA}, {CARGO}, alegando {MOTIVO}, conforme consta no {OFC_REFERENCIA}.

E o breve relatorio. Segue a manifestacao desta Coordenadoria.

Preliminarmente, convem informar que o(a) referido(a) servidor(a) {HISTORICO_MOVIMENTACOES},
conforme dossie, anexo, extraido do sistema MentoRH.

Era o que cabia informar.

Diante das informacoes apresentadas, encaminhamos os autos ao Gabinete da Diretora-Geral,
para analise e deliberacao.
```

## NOTA DE USO
`{HISTORICO_MOVIMENTACOES}` deve reproduzir a cadeia real de portarias/remocoes extraida do
MentoRH. Exemplo de forma: "foi relotado da unidade X para a unidade Y, Portaria NNNN/AAAA,
apos foi relotado para a unidade Z, Portaria NNNN/AAAA, desde DD/MM/AAAA".
Nunca preencher esse campo por inferencia — se ausente, marcar
`[DADO FALTANTE: historico de movimentacoes MentoRH]`.
