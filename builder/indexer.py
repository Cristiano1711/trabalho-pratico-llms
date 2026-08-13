"""Indexador — passo 1.10.

Fragmenta os documentos aprovados em chunks, calcula embeddings e popula
uma vector store ChromaDB, anexando a CADA chunk os metadados obrigatórios
do contrato MCP (Seção 3.1).

Decisões documentadas:
  - Vector store  : ChromaDB (persistente em data/chroma_index/)
  - Embeddings    : sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
                    (multilingual, leve, roda sem GPU)
  - Tamanho chunk : 512 tokens (~400 palavras) com overlap de 64 tokens
  - k padrão      : 5 chunks por query (configurável)
  - Seed          : 42 (reprodutibilidade, Seção 7)

O índice NÃO é versionado (Seção 6.4) — apenas os metadados por chunk
(data/chunks_meta.json) entram no repositório.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path

DISCIPLINE = "Cálculo II"
AREA = "Matemática — Licenciatura"

# ── Parâmetros de chunking ────────────────────────────────────────────────────
CHUNK_SIZE_TOKENS = 512
CHUNK_OVERLAP_TOKENS = 64
MIN_CHUNK_CHARS = 150    # chunks menores que isso são descartados

ROOT = Path(__file__).resolve().parent.parent
INDEX_DIR = ROOT / "data" / "chroma_index"
CHUNKS_META_PATH = ROOT / "data" / "chunks_meta.json"


@dataclass
class Chunk:
    chunk_id: str
    text: str
    source_url: str
    evaluator_score: float
    collected_at: str
    topics: list[str]
    raw_content_hash: str
    discipline: str
    area: str
    corpus_hash: str = ""   # preenchido pelo freeze


# ── Utilitários de chunking ───────────────────────────────────────────────────

def _tokenizar_simples(texto: str) -> list[str]:
    """Tokenização por espaços (rápida, sem dependências extras)."""
    return texto.split()


def _chunkar(texto: str, size: int = CHUNK_SIZE_TOKENS, overlap: int = CHUNK_OVERLAP_TOKENS) -> list[str]:
    """
    Divide o texto em chunks de `size` tokens com `overlap` de sobreposição.
    Tenta quebrar em parágrafos quando possível.
    """
    # Limpar espaços excessivos
    texto = re.sub(r"\n{3,}", "\n\n", texto.strip())
    paragrafos = [p.strip() for p in texto.split("\n\n") if p.strip()]

    chunks: list[str] = []
    buffer: list[str] = []
    buffer_tokens = 0

    for paragrafo in paragrafos:
        tokens_p = _tokenizar_simples(paragrafo)

        # Parágrafo cabe no buffer atual
        if buffer_tokens + len(tokens_p) <= size:
            buffer.append(paragrafo)
            buffer_tokens += len(tokens_p)
        else:
            # Salvar buffer atual se tiver conteúdo suficiente
            if buffer:
                chunk_text = "\n\n".join(buffer)
                if len(chunk_text) >= MIN_CHUNK_CHARS:
                    chunks.append(chunk_text)
                # Overlap: manter últimos tokens como início do próximo chunk
                overlap_words = _tokenizar_simples("\n\n".join(buffer))[-overlap:]
                buffer = [" ".join(overlap_words)] if overlap_words else []
                buffer_tokens = len(overlap_words)

            # Parágrafo muito longo: dividir por tokens
            if len(tokens_p) > size:
                for i in range(0, len(tokens_p), size - overlap):
                    pedaco = " ".join(tokens_p[i:i + size])
                    if len(pedaco) >= MIN_CHUNK_CHARS:
                        chunks.append(pedaco)
                buffer = []
                buffer_tokens = 0
            else:
                buffer = [paragrafo]
                buffer_tokens = len(tokens_p)

    # Flush do buffer final
    if buffer:
        chunk_text = "\n\n".join(buffer)
        if len(chunk_text) >= MIN_CHUNK_CHARS:
            chunks.append(chunk_text)

    return chunks


def _chunk_id(source_url: str, idx: int, text: str) -> str:
    """Gera chunk_id determinístico baseado em URL + índice + hash do texto."""
    base = f"{source_url}::chunk_{idx}::{hashlib.md5(text.encode()).hexdigest()[:8]}"
    return hashlib.sha256(base.encode()).hexdigest()[:16]


# ── Pipeline de indexação ─────────────────────────────────────────────────────

def build_index(evaluated_docs: list[dict]) -> list[Chunk]:
    """
    Fragmenta em chunks, calcula embeddings e popula a vector store ChromaDB.

    Parâmetros:
        evaluated_docs — lista de dicts com metadados + evaluator_score + aprovado
    """
    try:
        import chromadb
        from chromadb.utils import embedding_functions
    except ImportError:
        raise ImportError(
            "Instale as dependências: pip install chromadb sentence-transformers"
        )

    # Filtrar apenas aprovados
    aprovados = [d for d in evaluated_docs if d.get("aprovado", False)]
    print(f"✓ Indexando {len(aprovados)} documentos aprovados (de {len(evaluated_docs)} total)")

    # Inicializar ChromaDB persistente
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(INDEX_DIR))

    # Embedding multilingual leve (sem GPU)
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="paraphrase-multilingual-MiniLM-L12-v2"
    )

    # Criar/recriar coleção
    try:
        client.delete_collection("calculus2_corpus")
    except Exception:
        pass
    collection = client.create_collection(
        name="calculus2_corpus",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )

    todos_chunks: list[Chunk] = []

    for doc in aprovados:
        # Ler conteúdo bruto
        conteudo = ""
        raw_path = doc.get("raw_path", "")
        if raw_path:
            p = Path(raw_path)
            if not p.is_absolute():
                p = ROOT / raw_path
            if p.exists():
                conteudo = p.read_text(encoding="utf-8", errors="ignore")

        if not conteudo:
            print(f"  ⚠ sem conteúdo bruto para {doc.get('source_url', '?')[:60]}")
            continue

        pedacos = _chunkar(conteudo)
        if not pedacos:
            continue

        source_url = doc.get("source_url", "")
        score = doc.get("evaluator_score", 0.0)
        collected_at = doc.get("fetched_at", "")
        topics = doc.get("topic_ids", [])
        raw_hash = doc.get("content_hash", "")
        title = doc.get("title", "")

        chunks_doc: list[Chunk] = []
        ids, texts, metas = [], [], []

        for i, texto in enumerate(pedacos):
            cid = _chunk_id(source_url, i, texto)
            chunk = Chunk(
                chunk_id=cid,
                text=texto,
                source_url=source_url,
                evaluator_score=score,
                collected_at=collected_at,
                topics=topics,
                raw_content_hash=raw_hash,
                discipline=DISCIPLINE,
                area=AREA,
                corpus_hash="",  # preenchido pelo freeze
            )
            chunks_doc.append(chunk)
            ids.append(cid)
            texts.append(texto)
            metas.append({
                "source_url": source_url,
                "evaluator_score": score,
                "collected_at": collected_at,
                "topics": json.dumps(topics),
                "raw_content_hash": raw_hash,
                "discipline": DISCIPLINE,
                "area": AREA,
                "title": title,
                "source_kind": doc.get("source_kind", ""),
            })

        # Upsert em lotes de 50
        BATCH = 50
        for start in range(0, len(ids), BATCH):
            collection.upsert(
                ids=ids[start:start+BATCH],
                documents=texts[start:start+BATCH],
                metadatas=metas[start:start+BATCH],
            )

        todos_chunks.extend(chunks_doc)
        print(f"  ✓ {doc.get('source_kind','?'):<15} | {len(chunks_doc):>3} chunks | {source_url[:50]}")

    print(f"\n✓ Total indexado: {len(todos_chunks)} chunks em {INDEX_DIR}")
    return todos_chunks


def salvar_chunks_meta(chunks: list[Chunk]) -> None:
    """Persiste metadados dos chunks SEM o texto (não versionado o conteúdo)."""
    meta = [
        {k: v for k, v in asdict(c).items() if k != "text"}
        for c in chunks
    ]
    CHUNKS_META_PATH.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"✓ Metadados de {len(meta)} chunks salvos em {CHUNKS_META_PATH}")


if __name__ == "__main__":
    # Teste com doc simulado (sem ChromaDB real)
    print("Testando chunking...")
    texto_teste = "\n\n".join([
        f"Parágrafo {i}: " + "conteúdo de teste sobre cálculo multivariável. " * 20
        for i in range(10)
    ])
    chunks = _chunkar(texto_teste)
    print(f"✓ {len(chunks)} chunks gerados para texto de {len(texto_teste)} chars")
    for i, c in enumerate(chunks[:3]):
        print(f"  chunk {i}: {len(c.split())} tokens, {len(c)} chars")
