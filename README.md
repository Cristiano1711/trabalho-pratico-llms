# Agente Acadêmico de Conteúdo — Cálculo II
 
Agente de recuperação de conteúdo especializado em **Cálculo II (IEM021)**, pensado para alimentar
agentes tutores via protocolo **MCP**.
 
O projeto é dividido em duas peças temporalmente separadas:
 
1. **Construtor de corpus** (`/builder`) — pipeline offline que coleta, avalia, indexa e congela
   material acadêmico sobre Cálculo II a partir de fontes abertas.
2. **Servidor MCP read-only** (`/mcp_content`) — serve o corpus congelado através de três tools
   MCP, prontas para serem consumidas por qualquer agente tutor compatível.
`corpus_hash` de referência: `0de6afcabfce3f46c670dae07be95ecbcb9435376700601f2459842db48f2e09`
 
---
 
## Como funciona
 
```
Ementa IEM021  →  Planner de coleta  →  Coletor (6 fontes)  →  Avaliador  →  Dedup
                                                                        ↓
                                                    Índice ChromaDB + embeddings
                                                                        ↓
                                                         Corpus congelado (hash)
                                                                        ↓
                                                     Servidor MCP (read-only)
```
 
**Fontes coletadas:**
 
| Fonte | Tipo | Cobertura |
|---|---|---|
| Wikipedia PT | Enciclopédia | 11 artigos |
| OpenStax Calculus Vol 2/3 | Livro didático aberto | 7 páginas |
| MIT OCW 18.02 | Material universitário | 4 páginas |
| arXiv | Artigos didáticos | 4 abstracts |
 
**Modelo de embeddings:** `paraphrase-multilingual-MiniLM-L12-v2` (sentence-transformers, multilingual, sem GPU)
 
---
 
## Estrutura do repositório
 
```
.
├── builder/                  # Construtor de corpus (pipeline offline)
│   ├── __main__.py           # Orquestrador: python -m builder
│   ├── parse_ementa.py       # Parser da ementa → data/ementa_estruturada.json
│   ├── planner.py            # Planner de coleta → data/plano_coleta.json
│   ├── collector.py          # Coletor (6 fontes)
│   ├── evaluator.py          # Avaliador de fontes (score 0–1)
│   ├── dedup.py              # Deduplicador (hash + shingles Jaccard)
│   ├── indexer.py            # Indexador ChromaDB + embeddings
│   └── freeze.py             # Congelador (corpus_hash SHA-256)
├── mcp_content/               # Servidor MCP read-only
│   ├── __main__.py           # Entrypoint: python -m mcp_content
│   └── server.py             # Tools: list_topics, corpus_query, get_chunk
├── data/
│   ├── ementa.txt             # Ementa oficial IEM021 (texto selecionável)
│   ├── ementa_estruturada.json
│   ├── plano_coleta.json
│   ├── corpus_meta.json       # Hash + estado por tópico (corpus congelado)
│   ├── chunks_meta.json       # Metadados de cada chunk (sem texto bruto)
│   ├── collected_docs_meta.json
│   ├── collection_log.json
│   ├── raw/                   # Conteúdo bruto (não versionado)
│   └── chroma_index/          # Vector store (não versionado)
├── evaluation/                # Métricas de construção, contrato e integração
├── manifest.json
├── requirements.txt
└── LICENSE
```
 
---
 
## Setup
 
**Requisitos:** Python >= 3.10
 
```bash
git clone https://github.com/ed-icomp-ufam/trabalho-pr-tico-3-nlp-2026-01-trilha-b-natha-e-cristiano.git
cd trabalho-pr-tico-3-nlp-2026-01-trilha-b-natha-e-cristiano
 
python -m venv .venv
source .venv/bin/activate   # Linux/Mac
# .venv\Scripts\activate    # Windows
 
pip install -r requirements.txt
```
 
---
 
## Reproduzindo o corpus
 
> O conteúdo bruto (`data/raw/`) e o índice ChromaDB (`data/chroma_index/`) não são versionados.
> É necessário rodar o pipeline para regenerar o corpus localmente.
 
```bash
mkdir -p data/raw data/chroma_index
 
# Roda coleta → avaliação → indexação → congelamento (7 etapas, ~2 min)
python -m builder
```
 
Ao final, o pipeline imprime o `corpus_hash`. A seed é fixa (`42`, em `data/plano_coleta.json`)
para reprodutibilidade.
 
> **Nota sobre rate limits:** a Wikipedia aplica limite de requisições (HTTP 429). O coletor
> registra falhas em `data/collection_log.json` e segue em frente; numa segunda execução, artigos
> que falharam na primeira costumam ser coletados.
 
> **Nota sobre estabilidade:** como o corpus é regenerado localmente a cada execução e o rate
> limit da Wikipedia varia, o `corpus_hash` pode diferir entre execuções — a estrutura (7 tópicos,
> mesmas fontes-alvo) permanece estável.
 
---
 
## Rodando o servidor MCP
 
```bash
# O corpus precisa estar gerado (data/chroma_index/ presente)
python -m mcp_content
```
 
O servidor roda via stdio (transporte MCP padrão) e carrega o ChromaDB + embeddings na
inicialização (~10s).
 
**Tools expostas:**
 
| Tool | Assinatura | Descrição |
|---|---|---|
| `list_topics` | `()` | Lista tópicos, cobertura, credibilidade média e corpus_hash |
| `corpus_query` | `(query, k=5, filters=None)` | Busca semântica — retorna k chunks com metadados completos |
| `get_chunk` | `(chunk_id)` | Recupera um chunk específico por ID |
 
Todo chunk retornado inclui metadados como `chunk_id`, `source_url`, `evaluator_score`,
`collected_at`, `topics`, `raw_content_hash`, `discipline`, `area` e `corpus_hash`.
 
---
 
## Conectando um agente tutor (cliente MCP)
 
```json
{
  "mcpServers": {
    "calculo2-iem021": {
      "command": "python",
      "args": ["-m", "mcp_content"],
      "cwd": "<caminho-para-este-repositório>"
    }
  }
}
```
 
O servidor é read-only e não requer variáveis de ambiente.
 
---
 
## Validação com o kit de compatibilidade
 
```bash
cd ..
git clone https://github.com/ed-icomp-ufam/kit-compatibilidade-tp3.git kit-compatibilidade
cd kit-compatibilidade
pip install -r requirements.txt
 
python -m check_contract \
  --target "python -m mcp_content" \
  --target-cwd "../trabalho-pr-tico-3-nlp-2026-01-trilha-b-natha-e-cristiano"
 
python -m tutor_mock \
  --target "python -m mcp_content" \
  --target-cwd "../trabalho-pr-tico-3-nlp-2026-01-trilha-b-natha-e-cristiano"
```
 
---
 
## Sobre as fontes
 
As provas ENADE (INEP) usadas na avaliação **não são republicadas** neste repositório — apenas
referenciadas por edição/questão, com link para a prova oficial.
 
## Autores
 
Nathã Pinto e Cristiano Lima.
 
## Licença
 
MIT — ver [`LICENSE`](./LICENSE).
