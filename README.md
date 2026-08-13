# TP3 — Trilha B: Agente Acadêmico de Conteúdo

**Disciplina:** ICC220 / PPGINF528 — Tópicos Especiais em Recuperação de Informação — 2026/01  
**Professores:** André Carvalho e Altigran da Silva  
**Autores:** Nathã Pinto · Cristiano Lima  
**Grupo:** B-G1  
**Licença:** MIT (ver [`LICENSE`](./LICENSE))

---

## Sobre o projeto

Agente Acadêmico de Conteúdo especializado em **Cálculo II (IEM021)** da UFAM/ICE.  
Composto por duas peças temporalmente separadas:

1. **Construtor de corpus** (`/builder`) — pipeline offline que coleta, avalia, indexa e congela material acadêmico sobre Cálculo II
2. **Servidor MCP read-only** (`/mcp_content`) — serve o corpus congelado via três tools do contrato MCP (Seção 3.1 do enunciado)

**Disciplina-alvo:** Cálculo II (IEM021) — UFAM, Instituto de Ciências Exatas  
**Área ENADE:** Matemática  
**Edições ENADE utilizadas:** 2021 (Matemática — Licenciatura) e 2014 (Matemática — Bacharelado)  
**corpus_hash:** `0de6afcabfce3f46c670dae07be95ecbcb9435376700601f2459842db48f2e09`

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
├── mcp_content/              # Servidor MCP read-only
│   ├── __main__.py           # Entrypoint: python -m mcp_content
│   └── server.py             # Tools: list_topics, corpus_query, get_chunk
├── data/
│   ├── ementa.txt            # Ementa oficial IEM021 (texto selecionável)
│   ├── ementa_estruturada.json
│   ├── plano_coleta.json
│   ├── corpus_meta.json      # Hash + estado por tópico (corpus congelado)
│   ├── chunks_meta.json      # Metadados de cada chunk (sem texto bruto)
│   ├── collected_docs_meta.json
│   ├── collection_log.json
│   ├── raw/                  # Conteúdo bruto (NÃO versionado)
│   └── chroma_index/         # Vector store (NÃO versionado)
├── evaluation/
│   ├── construction/         # Métricas Camada 1
│   ├── contract/             # Resultado do check_contract
│   ├── mock_integration/     # Logs do tutor_mock
│   └── interop/              # Logs e relatórios da Fase 2 (A-P1, A-G1, A-G2)
├── manifest.json
├── requirements.txt
├── LICENSE
├── CHECKLIST.md
└── RELATORIO.pdf
```

---

## Setup do ambiente

**Requisitos:** Python >= 3.10

```bash
# 1. Clonar o repositório
git clone https://github.com/ed-icomp-ufam/trabalho-pr-tico-3-nlp-2026-01-trilha-b-natha-e-cristiano.git
cd trabalho-pr-tico-3-nlp-2026-01-trilha-b-natha-e-cristiano

# 2. Criar ambiente virtual
python -m venv .venv
source .venv/bin/activate   # Linux/Mac
# .venv\Scripts\activate    # Windows

# 3. Instalar dependências
pip install -r requirements.txt
```

---

## Reprodução do corpus (pipeline offline)

> O conteúdo bruto (`data/raw/`) e o índice ChromaDB (`data/chroma_index/`) **não são versionados**.  
> É necessário rodar o pipeline para regenerar o corpus localmente.

```bash
# Criar pastas necessárias
mkdir -p data/raw data/chroma_index

# Rodar o pipeline completo (coleta → avaliação → indexação → congelamento)
python -m builder
```

O pipeline executa 7 etapas em sequência e leva ~2 minutos. Ao final imprime o `corpus_hash`.  
Seed fixada em `42` (campo `seed` em `data/plano_coleta.json`) para reprodutibilidade.

**Fontes coletadas:**
| Fonte | Tipo | Cobertura |
|---|---|---|
| Wikipedia PT | Enciclopédia | 11 artigos |
| OpenStax Calculus Vol 2/3 | Livro didático aberto | 7 páginas |
| MIT OCW 18.02 | Material universitário | 4 páginas |
| arXiv | Artigos didáticos | 4 abstracts |

**Nota sobre rate limits:** A Wikipedia aplica limite de requisições (HTTP 429). O coletor registra as falhas em `data/collection_log.json` e continua. Numa segunda execução, artigos que falharam na primeira costumam ser coletados.

**Nota sobre estabilidade temporal:** como o `corpus` é regenerado localmente por cada execução e o *rate limit* da Wikipedia varia, o `corpus_hash` pode diferir entre execuções — a estrutura (7 tópicos, mesmas fontes-alvo) permanece estável. Detalhes em `RELATORIO.pdf`, Seção de Discussão.

---

## Executar o servidor MCP

```bash
# O corpus deve estar gerado (data/chroma_index/ presente)
python -m mcp_content
```

O servidor roda via stdio (transporte MCP padrão). Ele carrega o ChromaDB e os embeddings na inicialização (~10s).

**Tools expostas:**

| Tool | Assinatura | Descrição |
|---|---|---|
| `list_topics` | `()` | Lista tópicos, cobertura, credibilidade média e corpus_hash |
| `corpus_query` | `(query, k=5, filters=None)` | Busca semântica — retorna k chunks com metadados completos |
| `get_chunk` | `(chunk_id)` | Recupera chunk específico por ID |

**Modelo de embeddings:** `paraphrase-multilingual-MiniLM-L12-v2` (sentence-transformers, multilingual, sem GPU)

---

## Validação com o kit de compatibilidade

```bash
# Clonar o kit ao lado do repositório
cd ..
git clone https://github.com/ed-icomp-ufam/kit-compatibilidade-tp3.git kit-compatibilidade
cd kit-compatibilidade
pip install -r requirements.txt

# Rodar check_contract contra o servidor
python -m check_contract \
  --target "python -m mcp_content" \
  --target-cwd "../trabalho-pr-tico-3-nlp-2026-01-trilha-b-natha-e-cristiano"

# Rodar tutor_mock
python -m tutor_mock \
  --target "python -m mcp_content" \
  --target-cwd "../trabalho-pr-tico-3-nlp-2026-01-trilha-b-natha-e-cristiano"
```

---

## Configuração do cliente MCP

Para conectar um Agente Tutor (Trilha A) a este servidor, use a configuração:

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

## Metadados obrigatórios por chunk

Todo chunk retornado pelas tools contém:

| Campo | Descrição |
|---|---|
| `chunk_id` | Identificador SHA-256 único |
| `source_url` | URL de origem |
| `evaluator_score` | Score do avaliador (0.0–1.0) |
| `collected_at` | Data/hora de coleta (ISO 8601) |
| `topics` | Lista de topic\_ids da ementa associados |
| `raw_content_hash` | SHA-256 do conteúdo bruto |
| `discipline` | Cálculo II |
| `area` | Matemática — Licenciatura |
| `corpus_hash` | Hash do corpus congelado |

---

## Licença e atribuição

Este repositório é distribuído sob licença **MIT** (ver [`LICENSE`](./LICENSE)).  
Trabalho desenvolvido para a disciplina **ICC220/PPGINF528 — Tópicos Especiais em Recuperação de
Informação — UFAM, 2026/01**, sob orientação dos professores **André Carvalho** e **Altigran da
Silva**, por **Nathã Pinto** e **Cristiano Lima**.

As provas ENADE (INEP) utilizadas para avaliação **não são republicadas** neste repositório —
apenas referenciadas por edição/questão, com link para a prova oficial (ver `RELATORIO.pdf`).
