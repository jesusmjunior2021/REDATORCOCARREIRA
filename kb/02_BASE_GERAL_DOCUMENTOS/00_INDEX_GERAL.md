---
id: INDEX-GERAL-001
base: 02_BASE_GERAL_DOCUMENTOS
escopo: Toda a producao documental da COCARREIRA/CAEDNC - TJMA
versao: 1.0
origem: Pasta Drive COCARREIRA (parentId 1IlqIa3Jt2RMvocuHbRbqkGNn2VTV9zPw)
---

# INDICE GERAL — MODELOS DE DOCUMENTOS COCARREIRA/CAEDNC

## O QUE ESTA BASE RESPONDE
Um assistente carregado com esta base responde de imediato:
1. "Quais modelos de documento voces tem guardados?" -> tabela abaixo.
2. "Voce consegue redigir X?" -> se X estiver na coluna Tipologia, sim.
3. "Qual modelo se aplica ao meu caso?" -> ver `ARVORE_DECISAO_GERAL.md`.
4. "Quais dados voce precisa de mim?" -> ver `CAMPOS_CANONICOS.md`.

## CATALOGO DE MODELOS

| ID | Arquivo | Tipologia | Materia | Situacao coberta |
|---|---|---|---|---|
| MOD-REL-01 | MOD_REL_01_informacao_relotacao_sem_pendencias.md | INFORMACAO | Relotacao | Anuencia OK + certidao PAD negativa + sem movimentacao em 6 meses |
| MOD-REL-02 | MOD_REL_02_informacao_relotacao_com_diligencias.md | INFORMACAO | Relotacao | Falta anuencia e/ou certidao PAD — encaminha para diligencia |
| MOD-REL-03 | MOD_REL_03_informacao_alteracao_lotacao_exercicio.md | INFORMACAO | Alteracao de lotacao de exercicio | Pedido do proprio servidor |
| MOD-REL-04 | MOD_REL_04_informacao_alteracao_lotacao_multiplos.md | INFORMACAO | Alteracao de lotacao de exercicio | Pedido de gestor, varios servidores |
| MOD-REL-05 | MOD_REL_05_informacao_relotacao_por_autoridade.md | INFORMACAO | Relotacao | Requerida por Desembargador/Corregedor, com nota sobre 1o Grau |
| MOD-REL-06 | MOD_REL_06_informacao_nao_anuencia_chefia.md | INFORMACAO | Movimentacao | Chefia imediata se manifestou DESFAVORAVEL |
| MOD-REL-07 | MOD_REL_07_despacho_ausencia_anuencia_certidao_pad.md | DESPACHO | Relotacao/Disposicao | Abrir vista a chefia para anuencia |
| MOD-REL-08 | MOD_REL_08_despacho_expedir_portaria.md | DESPACHO | Relotacao | Cumprimento de decisao — expedir portaria |
| MOD-PER-01 | MOD_PER_01_informacao_permuta_sem_pendencias.md | INFORMACAO | Permuta | Requisitos preenchidos |
| MOD-PER-02 | MOD_PER_02_informacao_permuta_com_legislacao.md | INFORMACAO | Permuta | Com transcricao da legislacao (RESOL-GP 23/2010) |
| MOD-DEV-01 | MOD_DEV_01_informacao_devolucao_servidor.md | INFORMACAO | Devolucao de servidor | Gestor devolve servidor a Diretoria-Geral |
| MOD-REC-01 | MOD_REC_01_informacao_reconducao.md | INFORMACAO | Reconducao | Ex-servidor pede retorno ao cargo |
| MOD-REM-01 | MOD_REM_01_remocao_a_pedido.md | INFORMACAO | Remocao a pedido | Inclui variante por motivo de saude |
| MOD-GEN-01 | MOD_GEN_01_informacao_padrao.md | INFORMACAO | Generico | Esqueleto universal de INFORMACAO |
| MOD-GEN-02 | MOD_GEN_02_despacho_padrao.md | DESPACHO | Generico | Esqueleto universal de DESPACHO |
| MOD-GEN-03 | MOD_GEN_03_oficio_padrao.md | OFICIO | Generico | Comunicacao externa |
| MOD-GEN-04 | MOD_GEN_04_memorando_padrao.md | MEMORANDO | Generico | Comunicacao interna / resposta DigiDoc |
| MOD-GEN-05 | MOD_GEN_05_requerimento_padrao.md | REQUERIMENTO | Generico | Requerimento do servidor |

## SUBPASTAS DE ORIGEM NO DRIVE (mapeadas)
AUXILIO BOLSA, CURSOS, FLUXO DE PROCESSOS, PERMUTA, REMOCAO A PEDIDO, RELOTACAO,
REQUERIMENTOS, VERBAS RESCISORIAS, OFICIAL DE JUSTICA TEMPORARIO, INSTRUTORIA INTERNA,
MODELOS- INSTRUTORIA INTERNA, DEVOLUCAO DE SERVIDOR, CORREICAO, DOCUMENTOS DO DIGIDOC 2024,
APRESENTACOES DE PROCESSOS DA CAEDNC, Orcamento para 2023.

## LACUNAS DECLARADAS (nao inventar conteudo)
Materias com pasta no Drive porem sem modelo textual extraido nesta versao:
VERBAS RESCISORIAS, OFICIAL DE JUSTICA TEMPORARIO, INSTRUTORIA INTERNA, CURSOS,
CORREICAO, ORCAMENTO. Ao serem solicitadas, o agente deve usar `MOD_GEN_01`/`MOD_GEN_02`
e declarar `[MODELO NAO CATALOGADO: <materia>]`.
