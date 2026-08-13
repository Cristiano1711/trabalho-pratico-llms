"""Parser de ementa — passo 1.6.

Produz representação estruturada da ementa a partir do texto bruto, com ao
menos: (i) lista de tópicos e subtópicos, (ii) conceitos-chave por tópico,
(iii) pré-requisitos declarados, (iv) bibliografia citada.

Saída persistida em JSON e revisada manualmente; erros de extração são
registrados em extraction_errors.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# ── Conceitos-chave revisados manualmente por tópico ─────────────────────────
# A extração automática captura subtópicos; os conceitos-chave abaixo foram
# revisados manualmente para garantir cobertura semântica adequada ao ENADE.
_CONCEITOS_CHAVE: dict[str, list[str]] = {
    "derivacao-vetores-regra-cadeia": [
        "curva parametrizada", "vetor velocidade", "regra de derivação",
        "regra da cadeia", "curvatura", "raio de curvatura", "comprimento de arco",
    ],
    "funcoes-de-varias-variaveis": [
        "funções de várias variáveis", "curvas de nível", "derivadas parciais",
        "diferenciabilidade", "gradiente", "plano tangente",
        "derivada direcional", "lei da conservação",
    ],
    "funcoes-potenciais-integrais-de-linha": [
        "funções potenciais", "campo conservativo", "derivação sob a integral",
        "integrais de linha", "dependência do caminho",
    ],
    "derivadas-de-ordem-superior": [
        "derivadas parciais repetidas", "operadores diferenciais parciais",
        "fórmula de taylor", "hessiana", "derivadas de ordem superior",
    ],
    "maximos-e-minimos": [
        "pontos críticos", "máximos e mínimos", "forma quadrática",
        "multiplicadores de lagrange", "otimização com restrição",
    ],
    "integrais-multiplas-mudanca-de-variaveis": [
        "integrais duplas", "integrais repetidas", "integrais triplas",
        "mudança de variáveis", "jacobiano", "teorema de green",
    ],
    "formula-de-taylor-e-series": [
        "fórmula de taylor", "série de taylor", "funções logarítmicas",
        "funções exponenciais", "séries convergentes",
        "teste da razão", "teste da integral",
    ],
}


def _slugify(texto: str) -> str:
    """Converte título em topic_id slug."""
    texto = texto.lower()
    texto = re.sub(r"[áàâã]", "a", texto)
    texto = re.sub(r"[éêè]", "e", texto)
    texto = re.sub(r"[íîì]", "i", texto)
    texto = re.sub(r"[óôõò]", "o", texto)
    texto = re.sub(r"[úûù]", "u", texto)
    texto = re.sub(r"[ç]", "c", texto)
    texto = re.sub(r"[^a-z0-9]+", "-", texto)
    return texto.strip("-")


def _extrair_pre_requisitos(linhas: list[str], erros: list[dict]) -> list[str]:
    for linha in linhas:
        if linha.startswith("Pré-Requisitos:"):
            raw = linha.split(":", 1)[1].strip()
            # Remove códigos entre parênteses: "Cálculo I (IEM011)" → "Cálculo I"
            items = [re.sub(r"\s*\([^)]+\)", "", p).strip() for p in raw.split(";")]
            return [i for i in items if i]
    erros.append({"campo": "pre_requisitos", "erro": "linha não encontrada"})
    return []


def _extrair_topicos(texto: str, erros: list[dict]) -> list[dict]:
    match = re.search(r"Programa:(.*?)Bibliografia:", texto, re.DOTALL)
    if not match:
        erros.append({"campo": "programa", "erro": "bloco Programa/Bibliografia não encontrado"})
        return []

    bloco = match.group(1)
    padrao_topico = re.compile(r"^([IVX]+)\s*[–-]\s*(.+?)$", re.MULTILINE)
    matches = list(padrao_topico.finditer(bloco))

    if not matches:
        erros.append({"campo": "topicos", "erro": "nenhum tópico romano encontrado"})
        return []

    topicos = []
    for i, m in enumerate(matches):
        titulo = m.group(2).strip()
        topic_id = _slugify(titulo)

        inicio = m.end()
        fim = matches[i + 1].start() if i + 1 < len(matches) else len(bloco)
        bloco_topico = bloco[inicio:fim]

        subtopicos = [
            sub.group(2).strip()
            for sub in re.finditer(r"(\d+\.\d+)\.\s+(.+)", bloco_topico)
        ]

        if not subtopicos:
            erros.append({"campo": f"subtopicos_{topic_id}", "erro": "nenhum subtópico encontrado"})

        topicos.append({
            "topic_id": topic_id,
            "name": titulo,
            "subtopics": subtopicos,
            "key_concepts": _CONCEITOS_CHAVE.get(topic_id, []),
        })

    return topicos


def _extrair_bibliografia(texto: str, erros: list[dict]) -> list[str]:
    match = re.search(r"Bibliografia:(.*?)$", texto, re.DOTALL)
    if not match:
        erros.append({"campo": "bibliografia", "erro": "seção não encontrada"})
        return []
    refs = [l.strip() for l in match.group(1).splitlines() if l.strip()]
    return refs


def parse_ementa(raw_text: str) -> dict[str, Any]:
    """Converte o texto bruto da ementa em estrutura auditável."""
    erros: list[dict] = []
    linhas = [l.strip() for l in raw_text.splitlines() if l.strip()]

    # discipline e area
    discipline = "Cálculo II"
    area = "Matemática — Licenciatura"
    for linha in linhas:
        if linha.startswith("Disciplina:"):
            discipline = linha.split(":", 1)[1].strip()
        elif linha.startswith("Área (ENADE):"):
            area = linha.split(":", 1)[1].strip()

    pre_requisitos = _extrair_pre_requisitos(linhas, erros)
    topicos = _extrair_topicos(raw_text, erros)
    bibliografia = _extrair_bibliografia(raw_text, erros)

    return {
        "discipline": discipline,
        "area": area,
        "topics": topicos,
        "prerequisites": pre_requisitos,
        "bibliography": bibliografia,
        "extraction_errors": erros,
    }


def main() -> None:
    raw = Path("data/ementa.txt").read_text(encoding="utf-8")
    structured = parse_ementa(raw)
    out = Path("data/ementa_estruturada.json")
    out.write_text(json.dumps(structured, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ ementa estruturada escrita em {out}")
    print(f"✓ tópicos     : {len(structured['topics'])}")
    print(f"✓ subtópicos  : {sum(len(t['subtopics']) for t in structured['topics'])}")
    print(f"✓ erros       : {len(structured['extraction_errors'])}")
    if structured["extraction_errors"]:
        print("⚠ erros de extração:")
        for e in structured["extraction_errors"]:
            print(f"  [{e.get('campo')}] {e.get('erro')}")


if __name__ == "__main__":
    main()
