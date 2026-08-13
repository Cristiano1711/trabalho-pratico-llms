"""Avaliador de fontes — passo 1.9.

Heurística explícita que produz um score numérico (0.0–1.0) e uma justificativa
textual por documento, ambos persistidos.

Critérios e pesos:
  1. Domínio da fonte        (0.30) — fontes acadêmicas/educacionais reconhecidas
  2. Idioma                  (0.15) — PT preferido; EN aceito com penalidade leve
  3. Indícios de revisão     (0.25) — peer-review, editorial acadêmica, OCW
  4. Presença de autor       (0.15) — URL ou metadado com autor identificável
  5. Volume de conteúdo      (0.15) — texto suficiente para chunking útil

Score final = soma ponderada, arredondada em 2 casas.
Documentos com score < 0.40 são marcados como reprovados e não indexados.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

# ── Limiar de aprovação ───────────────────────────────────────────────────────
SCORE_MINIMO = 0.40

# ── Domínios confiáveis e seus pontos base ────────────────────────────────────
_DOMINIOS_CONFIAVEIS: dict[str, float] = {
    "wikipedia.org":       0.85,   # enciclopédia com revisão colaborativa
    "openstax.org":        1.00,   # livro didático aberto com revisão editorial
    "ocw.mit.edu":         1.00,   # MIT OpenCourseWare — material universitário
    "arxiv.org":           0.90,   # preprint revisado pela comunidade
    "khanacademy.org":     0.80,   # plataforma educacional reconhecida
    "scielo.org":          0.95,   # portal de revistas científicas revisadas
    "pt.khanacademy.org":  0.80,
    "en.wikipedia.org":    0.85,
    "pt.wikipedia.org":    0.85,
}

# ── Fontes por kind e seus atributos conhecidos ───────────────────────────────
_ATRIBUTOS_POR_KIND: dict[str, dict] = {
    "wikipedia_pt": {"tem_autor": False, "revisado": True,  "idioma": "pt"},
    "wikipedia_en": {"tem_autor": False, "revisado": True,  "idioma": "en"},
    "openstax":     {"tem_autor": True,  "revisado": True,  "idioma": "en"},
    "mit_ocw":      {"tem_autor": True,  "revisado": True,  "idioma": "en"},
    "arxiv":        {"tem_autor": True,  "revisado": True,  "idioma": "en"},
    "khan_academy": {"tem_autor": False, "revisado": True,  "idioma": "pt"},
}


@dataclass
class SourceEvaluation:
    score: float        # 0.0 a 1.0  (evaluator_score nos metadados do chunk)
    rationale: str      # justificativa textual persistida
    aprovado: bool      # score >= SCORE_MINIMO


def _score_dominio(url: str) -> tuple[float, str]:
    """Critério 1 — Domínio da fonte (peso 0.30)."""
    dominio = urlparse(url).netloc.lower().lstrip("www.")
    for d, base in _DOMINIOS_CONFIAVEIS.items():
        if dominio.endswith(d):
            return base * 0.30, f"domínio confiável ({dominio}={base:.2f})"
    return 0.10 * 0.30, f"domínio desconhecido ({dominio})"


def _score_idioma(source_kind: str, conteudo: str) -> tuple[float, str]:
    """Critério 2 — Idioma (peso 0.15). PT preferido, EN penalizado levemente."""
    attrs = _ATRIBUTOS_POR_KIND.get(source_kind, {})
    idioma = attrs.get("idioma", "?")

    # Detectar PT por palavras comuns
    palavras_pt = len(re.findall(
        r"\b(que|com|para|por|uma|não|mais|como|quando|também|são|ser|foi|tem)\b",
        conteudo[:2000], re.IGNORECASE
    ))
    if palavras_pt > 10:
        idioma = "pt"

    if idioma == "pt":
        return 1.00 * 0.15, "idioma português (preferido)"
    elif idioma == "en":
        return 0.75 * 0.15, "idioma inglês (aceito, leve penalidade)"
    return 0.50 * 0.15, f"idioma indeterminado"


def _score_revisao(source_kind: str) -> tuple[float, str]:
    """Critério 3 — Indícios de revisão por pares (peso 0.25)."""
    attrs = _ATRIBUTOS_POR_KIND.get(source_kind, {})
    if attrs.get("revisado"):
        motivos = {
            "openstax":     "livro didático com revisão editorial OpenStax",
            "mit_ocw":      "material de curso MIT com curadoria docente",
            "arxiv":        "preprint com revisão pela comunidade científica",
            "wikipedia_pt": "artigo Wikipedia com revisão colaborativa",
            "wikipedia_en": "artigo Wikipedia com revisão colaborativa",
            "khan_academy": "conteúdo Khan Academy com revisão pedagógica",
        }
        return 1.00 * 0.25, motivos.get(source_kind, "fonte com indícios de revisão")
    return 0.20 * 0.25, "sem indícios claros de revisão"


def _score_autor(source_kind: str, url: str) -> tuple[float, str]:
    """Critério 4 — Presença de autor identificável (peso 0.15)."""
    attrs = _ATRIBUTOS_POR_KIND.get(source_kind, {})
    if attrs.get("tem_autor"):
        return 1.00 * 0.15, "autor identificável nos metadados da fonte"
    # Wikipedia não lista autores individuais mas tem histórico
    if "wikipedia" in source_kind:
        return 0.70 * 0.15, "autoria coletiva rastreável via histórico Wikipedia"
    return 0.40 * 0.15, "autor não identificado"


def _score_volume(conteudo: str) -> tuple[float, str]:
    """Critério 5 — Volume de conteúdo útil (peso 0.15)."""
    n = len(conteudo.strip())
    if n >= 3000:
        return 1.00 * 0.15, f"conteúdo extenso ({n} chars)"
    elif n >= 1000:
        return 0.75 * 0.15, f"conteúdo moderado ({n} chars)"
    elif n >= 300:
        return 0.50 * 0.15, f"conteúdo mínimo ({n} chars)"
    return 0.10 * 0.15, f"conteúdo insuficiente ({n} chars)"


def evaluate(doc, conteudo: str = "") -> SourceEvaluation:
    """
    Avalia a credibilidade de um documento coletado.

    Parâmetros:
        doc       — CollectedDoc (ou dict com source_url, source_kind)
        conteudo  — texto bruto do documento (lido de data/raw/ quando disponível)
    """
    # Aceita tanto dataclass quanto dict
    if hasattr(doc, "source_url"):
        url = doc.source_url
        kind = doc.source_kind
    else:
        url = doc.get("source_url", "")
        kind = doc.get("source_kind", "")

    # Calcular cada critério
    s1, j1 = _score_dominio(url)
    s2, j2 = _score_idioma(kind, conteudo)
    s3, j3 = _score_revisao(kind)
    s4, j4 = _score_autor(kind, url)
    s5, j5 = _score_volume(conteudo)

    score_total = round(s1 + s2 + s3 + s4 + s5, 4)
    aprovado = score_total >= SCORE_MINIMO

    rationale = (
        f"[domínio={s1/0.30:.2f}×0.30] {j1} | "
        f"[idioma={s2/0.15:.2f}×0.15] {j2} | "
        f"[revisão={s3/0.25:.2f}×0.25] {j3} | "
        f"[autor={s4/0.15:.2f}×0.15] {j4} | "
        f"[volume={s5/0.15:.2f}×0.15] {j5} | "
        f"SCORE={score_total:.4f} → {'APROVADO' if aprovado else 'REPROVADO'}"
    )

    return SourceEvaluation(score=score_total, rationale=rationale, aprovado=aprovado)


def evaluate_all(docs: list, raw_dir: str = "data/raw") -> list[dict]:
    """
    Avalia todos os documentos coletados e retorna lista de dicts com
    os metadados enriquecidos (score + rationale + aprovado).
    """
    from pathlib import Path
    resultados = []

    for doc in docs:
        # Tentar ler o conteúdo bruto
        conteudo = ""
        raw_path = getattr(doc, "raw_path", None) or doc.get("raw_path", "")
        if raw_path:
            p = Path(raw_path)
            if not p.is_absolute():
                p = Path(raw_dir).parent.parent / raw_path
            if p.exists():
                conteudo = p.read_text(encoding="utf-8", errors="ignore")

        avaliacao = evaluate(doc, conteudo)

        # Montar dict com todos os metadados
        if hasattr(doc, "__dict__"):
            meta = {**doc.__dict__}
        else:
            meta = {**doc}

        meta["evaluator_score"] = avaliacao.score
        meta["evaluator_rationale"] = avaliacao.rationale
        meta["aprovado"] = avaliacao.aprovado
        resultados.append(meta)

    aprovados = sum(1 for r in resultados if r["aprovado"])
    print(f"✓ Avaliação: {len(resultados)} docs | {aprovados} aprovados | {len(resultados)-aprovados} reprovados")
    return resultados


if __name__ == "__main__":
    # Teste rápido com dados simulados
    from dataclasses import dataclass as dc

    @dc
    class DocFake:
        source_url: str
        source_kind: str
        raw_path: str = ""

    testes = [
        DocFake("https://pt.wikipedia.org/wiki/Derivada_parcial", "wikipedia_pt"),
        DocFake("https://openstax.org/books/calculus-volume-3/pages/4-3", "openstax"),
        DocFake("https://arxiv.org/abs/2309.00966", "arxiv"),
        DocFake("https://ocw.mit.edu/courses/18-02sc/", "mit_ocw"),
        DocFake("https://pt.khanacademy.org/math/calculus/", "khan_academy"),
        DocFake("https://blog-random.com/calculo", "unknown"),
    ]

    print(f"{'Fonte':<20} {'Score':>6}  Aprovado")
    print("-" * 50)
    for d in testes:
        ev = evaluate(d, conteudo="x" * 2000)
        print(f"{d.source_kind:<20} {ev.score:>6.4f}  {'✓' if ev.aprovado else '✗'}")
