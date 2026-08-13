"""Congelador — passo 1.10 / 1.12.

Encerra o pipeline offline:
  1. Calcula corpus_hash determinístico (SHA-256 sobre hashes de conteúdo ordenados)
  2. Preenche corpus_hash em todos os chunks e atualiza o índice ChromaDB
  3. Persiste data/corpus_meta.json com hash + contagem + memória da disciplina
  4. Persiste data/chunks_meta.json com metadados de cada chunk (sem texto bruto)

O corpus_hash é estável entre execuções dado o mesmo conjunto de documentos
(seed=42, ordenação determinística — Seção 7).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS_META_PATH = ROOT / "data" / "corpus_meta.json"
CHUNKS_META_PATH = ROOT / "data" / "chunks_meta.json"
INDEX_DIR = ROOT / "data" / "chroma_index"
DISCIPLINE = "Cálculo II"
AREA = "Matemática — Licenciatura"


def compute_corpus_hash(chunk_payloads: list[dict]) -> str:
    """Hash determinístico sobre os raw_content_hash dos chunks, ordenados."""
    raw_hashes = sorted(c["raw_content_hash"] for c in chunk_payloads)
    return hashlib.sha256(
        json.dumps(raw_hashes, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _calcular_topics_state(chunk_payloads: list[dict], ementa_path: Path) -> list[dict]:
    """
    Calcula o estado por tópico da ementa:
      - document_count : nº de chunks com aquele tópico
      - avg_credibility: média do evaluator_score dos chunks do tópico
      - coverage        : document_count / max_docs_total (do plano de coleta)
    """
    # Carregar tópicos da ementa
    ementa = json.loads((ROOT / "data" / "ementa_estruturada.json").read_text(encoding="utf-8"))
    topicos_ementa = {t["topic_id"]: t["name"] for t in ementa.get("topics", [])}

    # Tentar carregar max_docs_total do plano
    plano_path = ROOT / "data" / "plano_coleta.json"
    max_docs_por_topico = 15  # default
    if plano_path.exists():
        plano = json.loads(plano_path.read_text(encoding="utf-8"))
        max_docs_por_topico = plano.get("global_max_docs_per_topic", 15)

    # Agregar por tópico
    stats: dict[str, dict] = {
        tid: {"count": 0, "scores": []}
        for tid in topicos_ementa
    }

    for chunk in chunk_payloads:
        topics_raw = chunk.get("topics", [])
        # topics pode ser list ou string JSON
        if isinstance(topics_raw, str):
            try:
                topics_raw = json.loads(topics_raw)
            except Exception:
                topics_raw = [topics_raw]

        for tid in topics_raw:
            if tid in stats:
                stats[tid]["count"] += 1
                stats[tid]["scores"].append(chunk.get("evaluator_score", 0.0))

    topics_state = []
    for tid, name in topicos_ementa.items():
        count = stats[tid]["count"]
        scores = stats[tid]["scores"]
        avg_cred = round(sum(scores) / len(scores), 4) if scores else 0.0
        coverage = round(min(count / max_docs_por_topico, 1.0), 4)

        topics_state.append({
            "topic_id": tid,
            "name": name,
            "document_count": count,
            "avg_credibility": avg_cred,
            "coverage": coverage,
            "discipline": DISCIPLINE,
            "area": AREA,
        })

    return topics_state


def _atualizar_corpus_hash_no_chroma(corpus_hash: str) -> None:
    """Atualiza o campo corpus_hash em todos os chunks no ChromaDB."""
    if not INDEX_DIR.exists():
        return
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(INDEX_DIR))
        collection = client.get_collection("calculus2_corpus")
        # Buscar todos os IDs
        result = collection.get(include=["metadatas"])
        ids = result["ids"]
        metas = result["metadatas"]
        if not ids:
            return
        # Atualizar corpus_hash em cada metadado
        for m in metas:
            m["corpus_hash"] = corpus_hash
        collection.update(ids=ids, metadatas=metas)
        print(f"  ✓ corpus_hash atualizado em {len(ids)} chunks no ChromaDB")
    except Exception as exc:
        print(f"  ⚠ não foi possível atualizar ChromaDB: {exc}")


def freeze(chunk_payloads: list[dict], ementa_path: Path | None = None) -> str:
    """
    Congela o corpus: grava corpus_hash, metadados e memória da disciplina.

    Parâmetros:
        chunk_payloads — lista de dicts com metadados de cada chunk
        ementa_path    — caminho da ementa estruturada (default: data/ementa_estruturada.json)

    Retorna:
        corpus_hash — string SHA-256
    """
    if ementa_path is None:
        ementa_path = ROOT / "data" / "ementa_estruturada.json"

    corpus_hash = compute_corpus_hash(chunk_payloads)

    # Preencher corpus_hash em todos os chunks
    for c in chunk_payloads:
        c["corpus_hash"] = corpus_hash

    # Calcular estado por tópico
    topics_state = _calcular_topics_state(chunk_payloads, ementa_path)

    # Persistir corpus_meta.json
    corpus_meta = {
        "corpus_hash": corpus_hash,
        "congelado_em": datetime.now(timezone.utc).isoformat(),
        "discipline": DISCIPLINE,
        "area": AREA,
        "chunk_count": len(chunk_payloads),
        "topics_state": topics_state,
    }
    CORPUS_META_PATH.write_text(
        json.dumps(corpus_meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Persistir chunks_meta.json (sem texto bruto)
    chunks_sem_texto = [
        {k: v for k, v in c.items() if k != "text"}
        for c in chunk_payloads
    ]
    CHUNKS_META_PATH.write_text(
        json.dumps(chunks_sem_texto, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Atualizar ChromaDB se existir
    _atualizar_corpus_hash_no_chroma(corpus_hash)

    print(f"\n✓ Corpus congelado")
    print(f"  corpus_hash : {corpus_hash}")
    print(f"  chunks      : {len(chunk_payloads)}")
    print(f"  tópicos     : {len(topics_state)}")
    print(f"  corpus_meta : {CORPUS_META_PATH}")
    print(f"  chunks_meta : {CHUNKS_META_PATH}")
    return corpus_hash


if __name__ == "__main__":
    # Teste com chunks simulados
    chunks_teste = [
        {
            "chunk_id": f"chunk_{i:03d}",
            "source_url": f"https://pt.wikipedia.org/wiki/Topico_{i % 3}",
            "evaluator_score": 0.85,
            "collected_at": "2026-07-04T00:00:00Z",
            "topics": ["funcoes-de-varias-variaveis"] if i % 2 == 0 else ["maximos-e-minimos"],
            "raw_content_hash": hashlib.sha256(f"chunk_{i}".encode()).hexdigest(),
            "discipline": DISCIPLINE,
            "area": AREA,
            "corpus_hash": "",
        }
        for i in range(10)
    ]
    import hashlib
    h = freeze(chunks_teste)
    print(f"\nTeste OK — hash: {h[:16]}...")
