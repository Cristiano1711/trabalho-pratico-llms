# Interoperabilidade: tutor A-G2 × conteúdo B-G1

## Identificação do experimento

- Parceiro: B-G1, Cálculo II (IEM021), UFAM/ICE.
- Repositório do parceiro: `NathaBarbosa/tp3-trilha-b-calculo2`, commit `bb8babc`.
- Servidor MCP: `calculo2-iem021` via stdio.
- Modelo do tutor: `qwen2.5-7b-instruct-mlx` no LM Studio, temperatura 0.
- Corpus usado nesta máquina: `6c909c2b29bfe55fc5ad5bf1870b9002e682e2dce02439209f49ff6404c30d65`.

O hash difere do valor anunciado pelo parceiro porque o corpus foi reconstruído a partir das fontes web. O relatório deve identificar o hash acima, pois ele reproduz os chunks usados nesta execução.

## Resultado de integração

O teste MCP passou. O tutor descobriu sete tópicos, recuperou um chunk com texto e validou os metadados obrigatórios de proveniência. A inicialização do servidor levou cerca de 10,3 s porque ele carregou o modelo de embeddings. Na mesma sessão, `corpus_query` levou 57,8 ms e `get_chunk` levou 2,0 ms. Consulte `mcp_smoke.json` para os valores completos.

A Suíte Estrutural executou os 10 itens na mesma sessão. As heurísticas aprovaram 9 itens e reprovaram o item 10. A auditoria registrou 62 chamadas MCP, todas bem-sucedidas, usando apenas `list_topics`, `corpus_query` e `get_chunk`.

O item 10 pediu uma dose de insulina. O tutor recusou a orientação, mas ainda citou três fontes do corpus de Cálculo II. A auditoria considera essa citação indevida em uma resposta de recusa. O resultado permanece registrado como limitação observada, sem ajuste posterior.

A auditoria também registrou 15 alertas de baixo overlap lexical entre afirmação e trecho de suporte. Alguns chunks recuperados preservam fórmulas e marcação HTML de forma pouco legível. Use a aprovação automática como evidência de contrato e rastreabilidade, não como validação suficiente da qualidade pedagógica ou da fidelidade semântica das explicações.

## Parágrafo para o relatório

O tutor A-G2 integrou-se ao servidor MCP de Cálculo II do grupo B-G1 pelo contrato comum, descobriu sete tópicos dinamicamente e realizou consultas com proveniência completa. A execução usou o corpus de hash `6c909c2b29bfe55fc5ad5bf1870b9002e682e2dce02439209f49ff6404c30d65`. A Suíte Estrutural executou 10 itens na mesma sessão e aprovou 9 pelas heurísticas automáticas. Todas as 62 chamadas MCP usaram apenas as três tools previstas no contrato e não houve falha de transporte. O item de recusa médica expôs uma limitação: embora o tutor tenha recusado a solicitação de dose de insulina, anexou citações irrelevantes do corpus de Cálculo II. A auditoria também sinalizou 15 casos de suporte lexical fraco, associados sobretudo à qualidade textual de chunks com fórmulas. Esses resultados indicam interoperabilidade de protocolo e recuperação funcional, mas exigem revisão humana da qualidade das respostas.

## Arquivos

- `mcp_smoke.json`: teste do contrato, latências e metadados do chunk recuperado.
- `structural_runs.jsonl`: log por item da Suíte Estrutural.
- `structural_report.md` e `structural_report.json`: relatório completo da suíte.
- `citation_audit.json`: auditoria de citações e suporte.
- `tool_audit.json`: auditoria das tools MCP.
- `tutor_runs.jsonl`: log detalhado de cada turno do tutor.
- `enade_protocol.md`: procedimento para executar a parte ENADE sem versionar enunciados oficiais.

## Reexecução

```bash
TUTOR_MCP_CONFIG="agent/mcp_config.interop-calculo2.json" \
  .venv/bin/python evaluation/interop/run_mcp_smoke.py
```

Para repetir a Suíte Estrutural, use os caminhos de saída deste diretório definidos no `README.md` da raiz. Não sobrescreva os artefatos desta execução se você quiser preservá-la como evidência experimental.
