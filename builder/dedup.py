"""Deduplicador — passo 1.8 (complemento).

Remove documentos redundantes antes da indexação usando duas estratégias:
  1. Hash exato    — elimina cópias idênticas pelo content_hash
  2. Shingle hash  — detecta near-duplicates (similaridade Jaccard >= 0.85)

Estratégia documentada: shingles de 5 tokens, comparação par a par por tópico.
Não usa embeddings para manter o pipeline reprodutível sem GPU (seed=42).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path


# ── Parâmetros ────────────────────────────────────────────────────────────────
SHINGLE_SIZE = 5          # tamanho do n-grama de tokens
JACCARD_THRESHOLD = 0.85  # similaridade acima disso → duplicata


def _tokenizar(texto: str) -> list[str]:
    """Tokenização simples: lowercase + apenas alfanumérico."""
    return re.findall(r"[a-záéíóúâêîôûãõçà]+|\d+", texto.lower())


def _shingles(tokens: list[str], k: int = SHINGLE_SIZE) -> set[str]:
    """Gera conjunto de shingles (n-gramas de tokens) como strings."""
    return {" ".join(tokens[i:i+k]) for i in range(len(tokens) - k + 1)}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _ler_conteudo(doc: dict, raiz: Path) -> str:
    """Lê o conteúdo bruto do documento se disponível."""
    raw_path = doc.get("raw_path", "")
    if not raw_path:
        return ""
    p = Path(raw_path)
    if not p.is_absolute():
        p = raiz / raw_path
    if p.exists():
        return p.read_text(encoding="utf-8", errors="ignore")
    return ""


def deduplicate(docs: list[dict], raiz: str = ".") -> list[dict]:
    """
    Devolve a lista de documentos sem duplicatas.

    Etapa 1: remove por hash exato (content_hash).
    Etapa 2: remove near-duplicates por Jaccard de shingles.

    Parâmetros:
        docs  — lista de dicts com metadados (saída do evaluator)
        raiz  — caminho raiz do repositório para leitura de data/raw/
    """
    raiz_path = Path(raiz)
    removidos_hash = 0
    removidos_jaccard = 0

    # ── Etapa 1: dedup por hash exato ─────────────────────────────────────────
    vistos_hash: set[str] = set()
    unicos: list[dict] = []
    for doc in docs:
        h = doc.get("content_hash", "")
        if h and h in vistos_hash:
            removidos_hash += 1
            continue
        if h:
            vistos_hash.add(h)
        unicos.append(doc)

    # ── Etapa 2: dedup por shingles (near-duplicate) ──────────────────────────
    shingles_cache: list[tuple[int, set]] = []  # (índice, shingles)
    resultado: list[dict] = []
    indices_removidos: set[int] = set()

    for i, doc in enumerate(unicos):
        conteudo = _ler_conteudo(doc, raiz_path)
        if not conteudo:
            # Sem conteúdo bruto: usar source_url como proxy
            conteudo = doc.get("source_url", "")

        tokens = _tokenizar(conteudo[:5000])  # limitar para performance
        sh = _shingles(tokens)

        eh_dup = False
        for j, sh_j in shingles_cache:
            if j in indices_removidos:
                continue
            sim = _jaccard(sh, sh_j)
            if sim >= JACCARD_THRESHOLD:
                eh_dup = True
                indices_removidos.add(i)
                removidos_jaccard += 1
                break

        if not eh_dup:
            shingles_cache.append((i, sh))
            resultado.append(doc)

    total_removidos = removidos_hash + removidos_jaccard
    print(
        f"✓ Deduplicação: {len(docs)} entrada(s) → {len(resultado)} únicos "
        f"(removidos: {removidos_hash} por hash + {removidos_jaccard} por shingles)"
    )
    return resultado


if __name__ == "__main__":
    # Teste rápido com docs simulados
    docs_teste = [
        {"content_hash": "abc123", "source_url": "https://a.com", "raw_path": ""},
        {"content_hash": "abc123", "source_url": "https://a.com", "raw_path": ""},  # dup exata
        {"content_hash": "xyz999", "source_url": "https://b.com", "raw_path": ""},
        {"content_hash": "zzz000", "source_url": "https://c.com", "raw_path": ""},
    ]
    resultado = deduplicate(docs_teste)
    print(f"Resultado: {len(resultado)} docs únicos")
    for d in resultado:
        print(f"  {d['source_url']}")
