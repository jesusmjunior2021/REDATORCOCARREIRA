---
id: REGRAS-001
base: 02_BASE_GERAL_DOCUMENTOS
tipo: regras_operacionais
---

# REGRAS DE REDACAO, INDEXACAO E ANONIMIZACAO

## 1. FIDELIDADE
1.1 Nunca inventar nome, matricula, valor, edital, numero de processo, portaria,
    manifestacao ou informa.
1.2 Nunca alterar a ordem dos paragrafos dos modelos.
1.3 Nunca trocar nome ou matricula entre pecas do mesmo caso.
1.4 Toda peca gerada declara ao final o modelo-base usado (`ID`) e a norma invocada.

## 2. PAREAMENTO
2.1 Auxilio-Bolsa: MANIFESTACAO -> OFICIO, sempre nessa ordem.
2.2 Movimentacao funcional: INFORMACAO -> (DESPACHO de impulso, se houver diligencia).
2.3 Resposta DigiDoc: MEMORANDO ou OFICIO + INFORMACAO de suporte.

## 3. ANONIMIZACAO (para treino, exemplos e compartilhamento)
3.1 Substituir identificadores pessoais por placeholders sequenciais:
    `NAMEX1`, `NAMEX2` (nomes); `MATX1`, `MATX2` (matriculas); `CPFX1`; `PROCX1`.
3.2 A associacao placeholder <-> valor real fica em tabela separada, nunca no corpo do .md.
3.3 Documentos de producao (saida real para o DigiDoc) NAO sao anonimizados.
3.4 Todo exemplo incorporado a esta base de conhecimento entra ja anonimizado.

## 4. INDEXACAO E MEMORIA DO AGENTE
4.1 Cada documento gerado recebe uma chave:
    `{MATRICULA}_{NOME_SLUG}_{ASSUNTO_SLUG}_{AAAAMMDD}`
4.2 O historico e gravado em `HISTORICO_DOCUMENTOS.md` / planilha, com:
    data, tipologia, ID do modelo, servidor, matricula, assunto, processo, link do Doc.
4.3 A cada 10 documentos gerados para o mesmo servidor, o agente consolida um
    **perfil de servidor** (`PERFIL_{MATRICULA}.md`) com o historico de movimentacoes,
    beneficios e pendencias — util para detectar intersticio de 6 meses / 2 anos.
4.4 Inferencia dedutiva obrigatoria: antes de redigir, o agente consulta o historico e
    ALERTA se a movimentacao pretendida violar o intersticio.

## 5. NOMENCLATURA DA PASTA E DO ARQUIVO NO DRIVE (busca semantica)
```
Pasta:   {MATRICULA} - {NOME COMPLETO}
Arquivo: {MATRICULA}_{NOME COMPLETO}_{ASSUNTO}_{TIPOLOGIA}_{AAAA-MM-DD}
```
Exemplo: pasta `102350 - WENDEEL GOMES SARAIVA BARROSO`
         arquivo `102350_WENDEEL GOMES SARAIVA BARROSO_RELOTACAO_INFORMACAO_2026-08-06`

Isso garante que a busca por matricula, por nome ou por assunto recupere o documento.

## 6. TEMPERATURA E ESTILO
- temperature 0.2 (faixa 0.1-0.3), top_p 1.0, penalidades 0.0.
- Linguagem formal, impessoal, terceira pessoa, sem adjetivacao.
- Nao comprimir dados: todos os dados fornecidos pelo usuario devem aparecer na peca.
