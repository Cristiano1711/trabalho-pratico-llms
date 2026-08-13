"""Runner do pipeline offline do construtor de corpus: `python -m builder`.

Orquestra:
  1. parse_ementa  → data/ementa_estruturada.json
  2. planner       → data/plano_coleta.json
  3. collector     → data/raw/ (não versionado) + data/collection_log.json
  4. evaluator     → metadados enriquecidos com score + rationale
  5. dedup         → remove duplicatas
  6. indexer       → vector store ChromaDB + data/chunks_meta.json
  7. freeze        → data/corpus_meta.json com corpus_hash

Não usa MCP. Cada etapa persiste sua saída para auditoria.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run() -> None:
    inicio = time.time()
    print("=" * 60)
    print("  TP3 Trilha B — Pipeline de construção de corpus")
    print("  Disciplina: Cálculo II (IEM021) — UFAM")
    print("=" * 60)

    # ── 1. Parser ─────────────────────────────────────────────────────────────
    print("\n[1/7] Parser de ementa")
    from builder.parse_ementa import parse_ementa
    raw = (ROOT / "data" / "ementa.txt").read_text(encoding="utf-8")
    ementa = parse_ementa(raw)
    import json
    (ROOT / 'data' / 'ementa_estruturada.json').write_text(
        json.dumps(ementa, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    total_subtopicos = sum(len(t.get('subtopics', [])) for t in ementa.get('topics', []))
    print(f"  ✓ {len(ementa['topics'])} tópicos, {total_subtopicos} subtópicos")

    # ── 2. Planner ────────────────────────────────────────────────────────────
    print("\n[2/7] Planner de coleta")
    from builder.planner import build_plan
    plano = build_plan(ementa)
    total_q = sum(
        len(t["queries"]["pt"]) + len(t["queries"]["en"])
        for t in plano["topics"]
    )
    print(f"  ✓ {len(plano['topics'])} tópicos planejados, {total_q} queries")

    # ── 3. Coletor ────────────────────────────────────────────────────────────
    print("\n[3/7] Coletor de fontes")
    from builder.collector import collect, CollectedDoc
    docs_coletados = collect(plano)
    print(f"  ✓ {len(docs_coletados)} documentos coletados")

    # ── 4. Avaliador ──────────────────────────────────────────────────────────
    print("\n[4/7] Avaliador de fontes")
    from builder.evaluator import evaluate_all
    docs_dict = [asdict(d) for d in docs_coletados]
    docs_avaliados = evaluate_all(docs_dict, raw_dir=str(ROOT / "data" / "raw"))

    # Salvar metadados avaliados
    avaliados_path = ROOT / "data" / "collected_docs_meta.json"
    avaliados_path.write_text(
        json.dumps(docs_avaliados, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    aprovados = [d for d in docs_avaliados if d.get("aprovado")]
    print(f"  ✓ {len(aprovados)} aprovados de {len(docs_avaliados)} avaliados")

    # ── 5. Deduplicador ───────────────────────────────────────────────────────
    print("\n[5/7] Deduplicação")
    from builder.dedup import deduplicate
    docs_unicos = deduplicate(aprovados, raiz=str(ROOT))
    print(f"  ✓ {len(docs_unicos)} documentos únicos após dedup")

    # ── 6. Indexador ──────────────────────────────────────────────────────────
    print("\n[6/7] Indexação (ChromaDB + embeddings)")
    from builder.indexer import build_index, salvar_chunks_meta
    chunks = build_index(docs_unicos)
    salvar_chunks_meta(chunks)
    print(f"  ✓ {len(chunks)} chunks indexados")

    # ── 7. Congelador ─────────────────────────────────────────────────────────
    print("\n[7/7] Congelamento do corpus")
    from builder.freeze import freeze
    chunk_payloads = [asdict(c) for c in chunks]
    corpus_hash = freeze(chunk_payloads)

    # ── Resumo ────────────────────────────────────────────────────────────────
    tempo_total = round(time.time() - inicio, 2)
    print("\n" + "=" * 60)
    print("  Pipeline concluído")
    print(f"  Tempo total  : {tempo_total}s")
    print(f"  Docs únicos  : {len(docs_unicos)}")
    print(f"  Chunks       : {len(chunks)}")
    print(f"  corpus_hash  : {corpus_hash[:32]}...")
    print("=" * 60)


if __name__ == "__main__":
    run()
