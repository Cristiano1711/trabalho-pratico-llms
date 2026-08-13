"""Servidor MCP de conteúdo read-only — passo 1.11.

Implementa as três tools do contrato (Seção 3.1) sobre o corpus congelado:
  - list_topics()
  - corpus_query(query, k, filters)
  - get_chunk(chunk_id)

Transporte: stdio (FastMCP).
Corpus: ChromaDB persistente em data/chroma_index/ + data/corpus_meta.json.
Read-only: não expõe web_search, fetch, evaluate, index ou qualquer escrita.

Validar com o kit:
    cd ../kit-compatibilidade
    python -m check_contract --target "python -m mcp_content" \\
      --json "$OLDPWD/evaluation/contract/report.json"
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

# ── Caminhos ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
CORPUS_META_PATH = ROOT / "data" / "corpus_meta.json"
CHUNKS_META_PATH = ROOT / "data" / "chunks_meta.json"
INDEX_DIR = ROOT / "data" / "chroma_index"

# ── Envelopes do contrato ─────────────────────────────────────────────────────
def ok(data: dict) -> dict:
    return {"ok": True, "data": data}

def err(code: str, message: str, **extra) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, **extra}}

# ── Carregamento do corpus congelado ──────────────────────────────────────────

def _carregar_corpus_meta() -> dict:
    if not CORPUS_META_PATH.exists():
        return {}
    return json.loads(CORPUS_META_PATH.read_text(encoding="utf-8"))

def _carregar_chunks_meta() -> dict[str, dict]:
    """Carrega chunks_meta.json como dict indexado por chunk_id."""
    if not CHUNKS_META_PATH.exists():
        return {}
    chunks = json.loads(CHUNKS_META_PATH.read_text(encoding="utf-8"))
    return {c["chunk_id"]: c for c in chunks}

def _get_chroma_collection():
    """Retorna a coleção ChromaDB do corpus congelado (lazy, chamado só na 1ª query)."""
    if not INDEX_DIR.exists():
        return None
    try:
        import chromadb
        from chromadb.utils import embedding_functions
        client = chromadb.PersistentClient(path=str(INDEX_DIR))
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="paraphrase-multilingual-MiniLM-L12-v2"
        )
        return client.get_collection("calculus2_corpus", embedding_function=ef)
    except Exception:
        return None

# Estado global — tudo None até a primeira chamada de tool (lazy)
_corpus_meta: dict | None = None
_chunks_index: dict | None = None
_CORPUS_HASH: str = "NOT_FROZEN"
_collection = None
_loaded: bool = False

def _ensure_loaded() -> None:
    """Inicializa corpus e ChromaDB na primeira chamada (lazy loading)."""
    global _corpus_meta, _chunks_index, _CORPUS_HASH, _collection, _loaded
    if _loaded:
        return
    _loaded = True
    _corpus_meta = _carregar_corpus_meta()
    _chunks_index = _carregar_chunks_meta()
    _CORPUS_HASH = _corpus_meta.get("corpus_hash", "NOT_FROZEN") if _corpus_meta else "NOT_FROZEN"
    _collection = _get_chroma_collection()

# ── Servidor MCP ──────────────────────────────────────────────────────────────
mcp = FastMCP("agente-conteudo")


@mcp.tool()
def list_topics() -> dict:
    """
    Retorna os tópicos cobertos pelo agente de conteúdo e o estado por tópico:
    cobertura, número de documentos, credibilidade média, disciplina/área.
    """
    _ensure_loaded()
    if not _corpus_meta:
        return err("INDEX_INVALID", "corpus não encontrado — execute o pipeline builder primeiro")

    topics_state = _corpus_meta.get("topics_state", [])
    if not topics_state:
        return err("INDEX_INVALID", "topics_state ausente no corpus_meta.json")

    return ok({
        "discipline": _corpus_meta.get("discipline", "Cálculo II"),
        "area": _corpus_meta.get("area", "Matemática — Licenciatura"),
        "enade_editions": ["2021", "2017"],
        "corpus_hash": _CORPUS_HASH,
        "chunk_count": _corpus_meta.get("chunk_count", 0),
        "topics": [
            {
                "topic_id": t["topic_id"],
                "name": t["name"],
                "coverage": t.get("coverage", 0.0),
                "document_count": t.get("document_count", 0),
                "avg_credibility": t.get("avg_credibility", 0.0),
                "discipline": t.get("discipline", "Cálculo II"),
                "area": t.get("area", "Matemática — Licenciatura"),
            }
            for t in topics_state
        ],
    })


@mcp.tool()
def corpus_query(query: str, k: int = 5, filters: dict | None = None) -> dict:
    """
    Retorna os k chunks mais relevantes para a consulta,
    com proveniência completa nos metadados obrigatórios.

    Parâmetros:
        query   — texto da consulta (obrigatório, não vazio)
        k       — número de chunks a retornar (1–20, default 5)
        filters — filtros opcionais: {"topic_id": "...", "min_score": 0.7}
    """
    # ── Validações ────────────────────────────────────────────────────────────
    _ensure_loaded()
    if not isinstance(query, str) or not query.strip():
        return err("MALFORMED_QUERY", "parâmetro 'query' ausente ou vazio")
    if isinstance(k, bool) or not isinstance(k, int) or k <= 0:
        return err("INVALID_K", "parâmetro 'k' deve ser inteiro positivo")
    if k > 20:
        return err("INVALID_K", "parâmetro 'k' não pode exceder 20")
    if filters is not None and not isinstance(filters, dict):
        return err("INVALID_FILTERS", "parâmetro 'filters' deve ser objeto/dicionário")

    if not _corpus_meta:
        return err("INDEX_INVALID", "corpus não encontrado — execute o pipeline builder primeiro")

    # ── Filtros ChromaDB ──────────────────────────────────────────────────────
    where = None
    min_score = 0.0
    if filters:
        where_clauses = []
        if "topic_id" in filters:
            # topics é armazenado como JSON string no ChromaDB
            where_clauses.append(
                {"topics": {"$contains": filters["topic_id"]}}
            )
        if "source_kind" in filters:
            where_clauses.append(
                {"source_kind": {"$eq": filters["source_kind"]}}
            )
        if "min_score" in filters:
            try:
                min_score = float(filters["min_score"])
                where_clauses.append(
                    {"evaluator_score": {"$gte": min_score}}
                )
            except (ValueError, TypeError):
                return err("INVALID_FILTERS", "'min_score' deve ser número")
        if len(where_clauses) == 1:
            where = where_clauses[0]
        elif len(where_clauses) > 1:
            where = {"$and": where_clauses}

    # ── Busca na vector store ─────────────────────────────────────────────────
    if _collection is None:
        # Fallback: busca por keywords nos metadados quando ChromaDB indisponível
        return _fallback_query(query, k, filters or {})

    try:
        query_params: dict[str, Any] = {
            "query_texts": [query.strip()],
            "n_results": min(k, max(1, len(_chunks_index))),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            query_params["where"] = where

        result = _collection.query(**query_params)
    except Exception as exc:
        return err("INDEX_INVALID", f"erro ao consultar vector store: {exc}")

    # ── Montar resposta ───────────────────────────────────────────────────────
    ids = result.get("ids", [[]])[0]
    docs = result.get("documents", [[]])[0]
    metas = result.get("metadatas", [[]])[0]
    dists = result.get("distances", [[]])[0]

    chunks_resultado = []
    for cid, texto, meta, dist in zip(ids, docs, metas, dists):
        # topics foi armazenado como JSON string
        topics_raw = meta.get("topics", "[]")
        try:
            topics_list = json.loads(topics_raw) if isinstance(topics_raw, str) else topics_raw
        except Exception:
            topics_list = [topics_raw]

        chunks_resultado.append({
            "chunk_id": cid,
            "text": texto,
            "source_url": meta.get("source_url", ""),
            "evaluator_score": meta.get("evaluator_score", 0.0),
            "collected_at": meta.get("collected_at", ""),
            "topics": topics_list,
            "raw_content_hash": meta.get("raw_content_hash", ""),
            "discipline": meta.get("discipline", "Cálculo II"),
            "area": meta.get("area", "Matemática — Licenciatura"),
            "corpus_hash": _CORPUS_HASH,
            "similarity": round(1 - float(dist), 4),
        })

    return ok({
        "query": query,
        "k": k,
        "corpus_hash": _CORPUS_HASH,
        "chunks": chunks_resultado,
    })


@mcp.tool()
def get_chunk(chunk_id: str) -> dict:
    """
    Recupera um chunk específico por identificador.
    Retorna CHUNK_NOT_FOUND se o chunk_id não existir no corpus.
    """
    _ensure_loaded()
    if not isinstance(chunk_id, str) or not chunk_id.strip():
        return err("MALFORMED_QUERY", "parâmetro 'chunk_id' ausente ou vazio")

    chunk_id = chunk_id.strip()

    if not _corpus_meta:
        return err("INDEX_INVALID", "corpus não encontrado — execute o pipeline builder primeiro")

    # Buscar no ChromaDB
    if _collection is not None:
        try:
            result = _collection.get(
                ids=[chunk_id],
                include=["documents", "metadatas"],
            )
            ids = result.get("ids", [])
            if not ids:
                return err("CHUNK_NOT_FOUND", f"chunk_id '{chunk_id}' não encontrado no corpus")

            texto = result["documents"][0]
            meta = result["metadatas"][0]
            topics_raw = meta.get("topics", "[]")
            try:
                topics_list = json.loads(topics_raw) if isinstance(topics_raw, str) else topics_raw
            except Exception:
                topics_list = [topics_raw]

            return ok({
            "chunk": {
                "chunk_id": chunk_id,
                "text": texto,
                "source_url": meta.get("source_url", ""),
                "evaluator_score": meta.get("evaluator_score", 0.0),
                "collected_at": meta.get("collected_at", ""),
                "topics": topics_list,
                "raw_content_hash": meta.get("raw_content_hash", ""),
                "discipline": meta.get("discipline", "Cálculo II"),
                "area": meta.get("area", "Matemática — Licenciatura"),
                "corpus_hash": _CORPUS_HASH,
            }
        })
        except Exception as exc:
            return err("INDEX_INVALID", f"erro ao buscar chunk: {exc}")

    # Fallback: buscar nos metadados JSON
    if chunk_id in _chunks_index:
        meta = _chunks_index[chunk_id]
        return ok({
            "chunk": {
                **meta,
                "text": "[conteúdo não disponível sem vector store]",
                "corpus_hash": _CORPUS_HASH,
            }
        })

    return err("CHUNK_NOT_FOUND", f"chunk_id '{chunk_id}' não encontrado no corpus")


def _fallback_query(query: str, k: int, filters: dict) -> dict:
    """Busca por keywords nos metadados quando ChromaDB indisponível."""
    if not _chunks_index:
        return err("INDEX_INVALID", "corpus não encontrado e vector store indisponível")

    query_lower = query.lower()
    tokens_query = set(re.findall(r"[a-záéíóúâêîôûãõç]+", query_lower))

    scored = []
    for cid, meta in _chunks_index.items():
        topic_ids = meta.get("topics", [])
        if isinstance(topic_ids, str):
            try:
                topic_ids = json.loads(topic_ids)
            except Exception:
                topic_ids = [topic_ids]

        # Score simples: interseção de tokens com topic_ids
        topic_text = " ".join(topic_ids).lower()
        tokens_topic = set(re.findall(r"[a-záéíóúâêîôûãõç]+", topic_text))
        sim = len(tokens_query & tokens_topic) / max(len(tokens_query), 1)
        scored.append((sim, cid, meta))

    scored.sort(key=lambda x: -x[0])
    chunks_resultado = []
    for sim, cid, meta in scored[:k]:
        chunks_resultado.append({
            "chunk_id": cid,
            "text": "[vector store indisponível — reinstale chromadb]",
            "source_url": meta.get("source_url", ""),
            "evaluator_score": meta.get("evaluator_score", 0.0),
            "collected_at": meta.get("collected_at", ""),
            "topics": meta.get("topics", []),
            "raw_content_hash": meta.get("raw_content_hash", ""),
            "discipline": "Cálculo II",
            "area": "Matemática — Licenciatura",
            "corpus_hash": _CORPUS_HASH,
            "similarity": round(sim, 4),
        })

    return ok({"query": query, "k": k, "corpus_hash": _CORPUS_HASH, "chunks": chunks_resultado})


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
