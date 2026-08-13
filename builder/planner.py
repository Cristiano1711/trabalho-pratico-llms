"""Planner de coleta — passo 1.7.

Deriva um plano de coleta por tópico a partir da ementa estruturada.
O plano é persistido em data/plano_coleta.json e é auditável.

Para cada tópico define:
- queries de busca (português e inglês)
- fontes-alvo priorizadas
- limite de documentos por fonte
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ── Fontes disponíveis e seus pesos de prioridade ────────────────────────────
FONTES = [
    "wikipedia_pt",   # Wikipedia em português
    "wikipedia_en",   # Wikipedia em inglês (fallback terminologia)
    "openstax",       # OpenStax Calculus Vol 2 e 3
    "mit_ocw",        # MIT OpenCourseWare 18.02
    "arxiv",          # Artigos didáticos
    "khan_academy",   # Khan Academy (PT quando disponível)
]

# ── Queries por tópico (PT + EN para maximizar cobertura) ─────────────────────
_QUERIES_POR_TOPICO: dict[str, dict] = {
    "derivacao-de-vetores-e-regra-da-cadeia": {
        "queries_pt": [
            "curva parametrizada vetor velocidade cálculo",
            "regra da cadeia funções vetoriais",
            "curvatura raio de curvatura comprimento de arco",
        ],
        "queries_en": [
            "parametric curve velocity vector calculus",
            "chain rule vector functions multivariable",
            "curvature radius arc length parametric",
        ],
        "fontes_prioritarias": ["wikipedia_pt", "openstax", "mit_ocw", "wikipedia_en"],
    },
    "funcoes-de-varias-variaveis": {
        "queries_pt": [
            "funções de várias variáveis derivadas parciais",
            "gradiente diferenciabilidade cálculo multivariável",
            "plano tangente derivada direcional",
            "curvas de nível superfícies",
        ],
        "queries_en": [
            "multivariable functions partial derivatives",
            "gradient differentiability calculus",
            "tangent plane directional derivative",
            "level curves surfaces calculus",
        ],
        "fontes_prioritarias": ["wikipedia_pt", "openstax", "mit_ocw", "khan_academy"],
    },
    "funcoes-potenciais-e-integrais-de-linha": {
        "queries_pt": [
            "funções potenciais campo conservativo",
            "integrais de linha trabalho campo vetorial",
            "dependência do caminho integral de linha",
        ],
        "queries_en": [
            "potential functions conservative field calculus",
            "line integrals work vector field",
            "path independence line integral",
        ],
        "fontes_prioritarias": ["wikipedia_pt", "openstax", "mit_ocw", "wikipedia_en"],
    },
    "derivadas-de-ordem-superior": {
        "queries_pt": [
            "derivadas parciais repetidas teorema de schwarz",
            "operadores diferenciais parciais laplaciano",
            "fórmula de taylor funções de várias variáveis",
            "hessiana matriz jacobiana",
        ],
        "queries_en": [
            "higher order partial derivatives mixed partials",
            "partial differential operators Laplacian",
            "Taylor formula multivariable functions",
            "Hessian matrix second derivatives",
        ],
        "fontes_prioritarias": ["wikipedia_pt", "openstax", "mit_ocw", "arxiv"],
    },
    "maximos-e-minimos": {
        "queries_pt": [
            "máximos e mínimos funções de várias variáveis",
            "pontos críticos forma quadrática teste hessiana",
            "multiplicadores de lagrange otimização com restrição",
        ],
        "queries_en": [
            "maxima minima multivariable functions critical points",
            "quadratic form Hessian test saddle point",
            "Lagrange multipliers constrained optimization",
        ],
        "fontes_prioritarias": ["wikipedia_pt", "openstax", "khan_academy", "mit_ocw"],
    },
    "integrais-multiplas-mudanca-de-variaveis-em-integrais": {
        "queries_pt": [
            "integrais duplas triplas Fubini",
            "mudança de variáveis coordenadas polares cilíndricas esféricas",
            "teorema de green integral dupla",
            "jacobiano transformação de coordenadas",
        ],
        "queries_en": [
            "double triple integrals Fubini theorem",
            "change of variables polar cylindrical spherical coordinates",
            "Green theorem double integral",
            "Jacobian coordinate transformation",
        ],
        "fontes_prioritarias": ["wikipedia_pt", "openstax", "mit_ocw", "khan_academy"],
    },
    "a-formula-de-taylor-e-series": {
        "queries_pt": [
            "fórmula de Taylor série de Taylor funções reais",
            "séries numéricas convergência divergência",
            "teste da razão teste da integral convergência",
            "série de Taylor logaritmo exponencial",
        ],
        "queries_en": [
            "Taylor series formula remainder term",
            "numerical series convergence divergence tests",
            "ratio test integral test series",
            "Taylor series logarithm exponential functions",
        ],
        "fontes_prioritarias": ["wikipedia_pt", "openstax", "mit_ocw", "arxiv"],
    },
}


def build_plan(structured_ementa: dict[str, Any]) -> dict[str, Any]:
    """Gera o plano de coleta por tópico."""
    topics_plan = []

    for topico in structured_ementa.get("topics", []):
        topic_id = topico["topic_id"]
        config = _QUERIES_POR_TOPICO.get(topic_id, {})

        topics_plan.append({
            "topic_id": topic_id,
            "name": topico["name"],
            "queries": {
                "pt": config.get("queries_pt", []),
                "en": config.get("queries_en", []),
            },
            "target_sources": config.get("fontes_prioritarias", FONTES),
            "max_docs_per_source": 3,
            "max_docs_total": 15,
            "min_docs_required": 3,   # N mínimo para cobertura (Seção 4.3)
        })

    return {
        "version": 1,
        "seed": 42,
        "discipline": structured_ementa.get("discipline", "Cálculo II"),
        "area": structured_ementa.get("area", "Matemática — Licenciatura"),
        "sources_available": FONTES,
        "global_max_docs_per_topic": 15,
        "topics": topics_plan,
    }


def main() -> None:
    ementa = json.loads(Path("data/ementa_estruturada.json").read_text(encoding="utf-8"))
    plan = build_plan(ementa)
    out = Path("data/plano_coleta.json")
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ plano de coleta escrito em {out}")
    print(f"✓ tópicos planejados: {len(plan['topics'])}")
    total_queries = sum(
        len(t["queries"]["pt"]) + len(t["queries"]["en"])
        for t in plan["topics"]
    )
    print(f"✓ total de queries  : {total_queries}")
    print(f"✓ fontes disponíveis: {len(FONTES)}")


if __name__ == "__main__":
    main()
