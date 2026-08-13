# Protocolo ENADE para o parceiro B-G1

O parceiro disponibiliza uma curadoria com 20 referências ENADE, incluindo número, edição, tipo, tópico, gabarito e URL oficial. O arquivo não traz os enunciados completos, em conformidade com a restrição de não republicá-los no repositório.

## Como executar

1. Abra as provas oficiais indicadas em `../tp3-trilha-b-calculo2/evaluation/content/enade_curadoria_calculo2.json`.
2. Use os 20 itens curados em uma sessão local. Não adicione o texto integral das questões ao Git.
3. Para cada item, envie o enunciado ao tutor com a configuração `agent/mcp_config.interop-calculo2.json` e a skill `tutor-simulado`.
4. Registre somente: edição, número da questão, tópico, tipo, gabarito, resposta do tutor, acerto, fontes citadas, hash do corpus e observações.
5. Para itens discursivos, faça a avaliação humana prevista no enunciado com dois avaliadores e registre a concordância.

## Planilha sugerida

| prova | questão | tópico | tipo | gabarito | resposta do tutor | acerto | fontes válidas | observação |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ENADE Matemática |  |  |  |  |  |  |  |  |

## Estado atual

A parte ENADE ainda não foi executada. O impedimento é documental, não técnico: faltam os enunciados oficiais em uma sessão local de avaliação. A curadoria do B-G1 já fornece os 20 identificadores e gabaritos necessários para conduzir o experimento sem republicar as questões.
