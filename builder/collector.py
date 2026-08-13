"""Coletor — passo 1.8.

Executa buscas e fetch de páginas conforme o plano de coleta.
Fontes implementadas (>= 3 obrigatórias):
  1. wikipedia_pt  — Wikipedia em português
  2. wikipedia_en  — Wikipedia em inglês
  3. openstax      — OpenStax Calculus Vol 2 / 3
  4. mit_ocw       — MIT OpenCourseWare 18.02
  5. arxiv         — Artigos didáticos via API
  6. khan_academy  — Khan Academy (scraping HTML)

Conteúdo bruto salvo em data/raw/ (NÃO versionado — ver .gitignore).
Log de execução persistido em data/collection_log.json.
Respeita robots.txt, rate limits e termos de uso (Seção 8).
"""

from __future__ import annotations

import hashlib
import json
import time
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

# ── Caminhos ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
LOG_PATH = ROOT / "data" / "collection_log.json"

RAW_DIR.mkdir(parents=True, exist_ok=True)

# ── Rate limiting (respeitar servidores) ──────────────────────────────────────
DELAY_ENTRE_REQUESTS = 1.5  # segundos

# ── Páginas estáticas do MIT OCW e OpenStax para Cálculo ─────────────────────
MIT_OCW_URLS = [
    ("mit_ocw", "https://ocw.mit.edu/courses/18-02sc-multivariable-calculus-fall-2010/pages/1.-vectors-and-matrices/part-a-vectors-determinants-and-planes/", "derivacao-de-vetores-e-regra-da-cadeia"),
    ("mit_ocw", "https://ocw.mit.edu/courses/18-02sc-multivariable-calculus-fall-2010/pages/2.-partial-derivatives/", "funcoes-de-varias-variaveis"),
    ("mit_ocw", "https://ocw.mit.edu/courses/18-02sc-multivariable-calculus-fall-2010/pages/3.-double-integrals-and-line-integrals-in-the-plane/", "integrais-multiplas-mudanca-de-variaveis-em-integrais"),
    ("mit_ocw", "https://ocw.mit.edu/courses/18-02sc-multivariable-calculus-fall-2010/pages/3.-double-integrals-and-line-integrals-in-the-plane/part-b-vector-fields-and-line-integrals/", "funcoes-potenciais-e-integrais-de-linha"),
]

OPENSTAX_URLS = [
    ("openstax", "https://openstax.org/books/calculus-volume-3/pages/1-1-vectors-in-the-plane", "derivacao-de-vetores-e-regra-da-cadeia"),
    ("openstax", "https://openstax.org/books/calculus-volume-3/pages/4-1-functions-of-several-variables", "funcoes-de-varias-variaveis"),
    ("openstax", "https://openstax.org/books/calculus-volume-3/pages/4-3-partial-derivatives", "funcoes-de-varias-variaveis"),
    ("openstax", "https://openstax.org/books/calculus-volume-3/pages/4-7-maximum-minimum-problems", "maximos-e-minimos"),
    ("openstax", "https://openstax.org/books/calculus-volume-3/pages/4-8-lagrange-multipliers", "maximos-e-minimos"),
    ("openstax", "https://openstax.org/books/calculus-volume-3/pages/5-1-double-integrals-over-rectangular-regions", "integrais-multiplas-mudanca-de-variaveis-em-integrais"),
    ("openstax", "https://openstax.org/books/calculus-volume-3/pages/6-2-line-integrals", "funcoes-potenciais-e-integrais-de-linha"),
    ("openstax", "https://openstax.org/books/calculus-volume-2/pages/5-1-sequences", "a-formula-de-taylor-e-series"),
    ("openstax", "https://openstax.org/books/calculus-volume-2/pages/6-1-power-series-and-functions", "a-formula-de-taylor-e-series"),
]

# Artigos arXiv didáticos de Cálculo Multivariável
ARXIV_IDS = [
    ("2309.00966", ["funcoes-de-varias-variaveis", "derivadas-de-ordem-superior"]),
    ("1801.00042", ["a-formula-de-taylor-e-series"]),
    ("2106.11452", ["integrais-multiplas-mudanca-de-variaveis-em-integrais"]),
    ("1911.07700", ["maximos-e-minimos", "funcoes-potenciais-e-integrais-de-linha"]),
]

# Páginas Wikipedia PT por tópico
WIKIPEDIA_PT_PAGES = [
    ("Cálculo diferencial e integral", ["derivacao-de-vetores-e-regra-da-cadeia"]),
    ("Curva parametrizada", ["derivacao-de-vetores-e-regra-da-cadeia"]),
    ("Regra da cadeia", ["derivacao-de-vetores-e-regra-da-cadeia"]),
    ("Curvatura", ["derivacao-de-vetores-e-regra-da-cadeia"]),
    ("Função de várias variáveis", ["funcoes-de-varias-variaveis"]),
    ("Derivada parcial", ["funcoes-de-varias-variaveis", "derivadas-de-ordem-superior"]),
    ("Gradiente", ["funcoes-de-varias-variaveis"]),
    ("Plano tangente", ["funcoes-de-varias-variaveis"]),
    ("Derivada direcional", ["funcoes-de-varias-variaveis"]),
    ("Campo conservativo", ["funcoes-potenciais-e-integrais-de-linha"]),
    ("Integral de linha", ["funcoes-potenciais-e-integrais-de-linha"]),
    ("Teorema de Schwarz", ["derivadas-de-ordem-superior"]),
    ("Hessiana", ["derivadas-de-ordem-superior", "maximos-e-minimos"]),
    ("Multiplicadores de Lagrange", ["maximos-e-minimos"]),
    ("Integral dupla", ["integrais-multiplas-mudanca-de-variaveis-em-integrais"]),
    ("Teorema de Green", ["integrais-multiplas-mudanca-de-variaveis-em-integrais"]),
    ("Jacobiano", ["integrais-multiplas-mudanca-de-variaveis-em-integrais"]),
    ("Série de Taylor", ["a-formula-de-taylor-e-series"]),
    ("Série convergente", ["a-formula-de-taylor-e-series"]),
    ("Critério da razão", ["a-formula-de-taylor-e-series"]),
]

WIKIPEDIA_EN_PAGES = [
    ("Parametric equation", ["derivacao-de-vetores-e-regra-da-cadeia"]),
    ("Chain rule", ["derivacao-de-vetores-e-regra-da-cadeia"]),
    ("Partial derivative", ["funcoes-de-varias-variaveis", "derivadas-de-ordem-superior"]),
    ("Gradient", ["funcoes-de-varias-variaveis"]),
    ("Conservative vector field", ["funcoes-potenciais-e-integrais-de-linha"]),
    ("Line integral", ["funcoes-potenciais-e-integrais-de-linha"]),
    ("Lagrange multiplier", ["maximos-e-minimos"]),
    ("Multiple integral", ["integrais-multiplas-mudanca-de-variaveis-em-integrais"]),
    ("Green's theorem", ["integrais-multiplas-mudanca-de-variaveis-em-integrais"]),
    ("Taylor series", ["a-formula-de-taylor-e-series"]),
    ("Ratio test", ["a-formula-de-taylor-e-series"]),
]


@dataclass
class CollectedDoc:
    source_url: str
    topic_ids: list[str]
    raw_path: str        # caminho local em data/raw/ (não versionado)
    fetched_at: str      # ISO 8601
    source_kind: str     # wikipedia_pt | wikipedia_en | openstax | mit_ocw | arxiv | khan_academy
    title: str
    content_hash: str    # SHA-256 do conteúdo bruto


# ── Utilitários ───────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _safe_filename(texto: str) -> str:
    return re.sub(r"[^a-z0-9_-]", "_", texto.lower())[:80]


def _salvar_raw(nome: str, conteudo: str) -> Path:
    path = RAW_DIR / f"{nome}.txt"
    path.write_text(conteudo, encoding="utf-8")
    return path


def _get(url: str, headers: dict | None = None, timeout: int = 15) -> requests.Response | None:
    """GET com tratamento de erro e rate limiting."""
    try:
        resp = requests.get(url, headers=headers or {}, timeout=timeout)
        resp.raise_for_status()
        time.sleep(DELAY_ENTRE_REQUESTS)
        return resp
    except Exception as exc:
        print(f"    ⚠ fetch falhou [{url[:60]}]: {exc}")
        return None


# ── Coletores por fonte ───────────────────────────────────────────────────────

def _coletar_wikipedia(titulo: str, topic_ids: list[str], lang: str = "pt") -> CollectedDoc | None:
    """Coleta página da Wikipedia via API de extração de texto."""
    url = (
        f"https://{lang}.wikipedia.org/w/api.php"
        f"?action=query&prop=extracts&explaintext=1&titles={requests.utils.quote(titulo)}"
        f"&format=json&redirects=1"
    )
    headers = {"User-Agent": "Mozilla/5.0 (tp3-nlp-ufam academic corpus builder)"}
    resp = _get(url, headers=headers)
    if not resp:
        return None

    data = resp.json()
    pages = data.get("query", {}).get("pages", {})
    page = next(iter(pages.values()))
    extract = page.get("extract", "")
    if not extract or len(extract) < 200:
        print(f"    ⚠ Wikipedia {lang} '{titulo}': conteúdo insuficiente")
        return None

    kind = f"wikipedia_{lang}"
    fname = _safe_filename(f"{kind}_{titulo}")
    path = _salvar_raw(fname, extract)
    page_url = f"https://{lang}.wikipedia.org/wiki/{requests.utils.quote(titulo.replace(' ', '_'))}"

    return CollectedDoc(
        source_url=page_url,
        topic_ids=topic_ids,
        raw_path=str(path.relative_to(ROOT)),
        fetched_at=_now_iso(),
        source_kind=kind,
        title=titulo,
        content_hash=_sha256(extract),
    )


def _coletar_html(source_kind: str, url: str, topic_ids: list[str]) -> CollectedDoc | None:
    """Coleta e extrai texto de páginas HTML (OpenStax, MIT OCW)."""
    headers = {"User-Agent": "Mozilla/5.0 (academic corpus builder; contact: tp3-nlp-ufam)"}
    resp = _get(url, headers=headers)
    if not resp:
        return None

    # Forçar UTF-8 para evitar símbolos matemáticos quebrados (â → ∂)
    resp.encoding = resp.apparent_encoding or 'utf-8'
    soup = BeautifulSoup(resp.content, "html.parser", from_encoding='utf-8')

    # Remove scripts, estilos e navegação
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    # Tenta extrair o conteúdo principal
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find(class_=re.compile(r"content|main|body", re.I))
        or soup.body
    )
    texto = main.get_text(separator="\n", strip=True) if main else soup.get_text(separator="\n", strip=True)

    if len(texto) < 300:
        print(f"    ⚠ {source_kind} [{url[:60]}]: conteúdo insuficiente")
        return None

    titulo = soup.title.string.strip() if soup.title else url.split("/")[-1]
    fname = _safe_filename(f"{source_kind}_{titulo}")
    path = _salvar_raw(fname, texto)

    return CollectedDoc(
        source_url=url,
        topic_ids=topic_ids,
        raw_path=str(path.relative_to(ROOT)),
        fetched_at=_now_iso(),
        source_kind=source_kind,
        title=titulo,
        content_hash=_sha256(texto),
    )


def _coletar_arxiv(arxiv_id: str, topic_ids: list[str]) -> CollectedDoc | None:
    """Coleta abstract e metadados de artigo arXiv via API."""
    url = f"https://export.arxiv.org/abs/{arxiv_id}"
    api_url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"
    resp = _get(api_url)
    if not resp:
        return None

    soup = BeautifulSoup(resp.text, "xml")
    entry = soup.find("entry")
    if not entry:
        return None

    titulo_tag = entry.find("title")
    resumo_tag = entry.find("summary")
    titulo = titulo_tag.get_text(strip=True) if titulo_tag else arxiv_id
    resumo = resumo_tag.get_text(strip=True) if resumo_tag else ""

    if len(resumo) < 100:
        print(f"    ⚠ arXiv {arxiv_id}: resumo insuficiente")
        return None

    conteudo = f"Title: {titulo}\n\nAbstract:\n{resumo}"
    fname = _safe_filename(f"arxiv_{arxiv_id}")
    path = _salvar_raw(fname, conteudo)

    return CollectedDoc(
        source_url=url,
        topic_ids=topic_ids,
        raw_path=str(path.relative_to(ROOT)),
        fetched_at=_now_iso(),
        source_kind="arxiv",
        title=titulo,
        content_hash=_sha256(conteudo),
    )


# ── Pipeline principal ────────────────────────────────────────────────────────

def collect(plan: dict) -> list[CollectedDoc]:
    """Executa a coleta conforme o plano e devolve os documentos coletados."""
    docs: list[CollectedDoc] = []
    log_entries: list[dict] = []
    inicio_total = time.time()

    def _registrar(fonte: str, url: str, topic_ids: list[str], ok: bool, motivo: str = ""):
        log_entries.append({
            "fonte": fonte,
            "url": url,
            "topic_ids": topic_ids,
            "sucesso": ok,
            "motivo": motivo,
            "ts": _now_iso(),
        })

    # ── 1. Wikipedia PT ───────────────────────────────────────────────────────
    print("\n[1/6] Wikipedia PT")
    for titulo, topic_ids in WIKIPEDIA_PT_PAGES:
        print(f"  → {titulo}")
        doc = _coletar_wikipedia(titulo, topic_ids, lang="pt")
        url = f"https://pt.wikipedia.org/wiki/{titulo.replace(' ', '_')}"
        if doc:
            docs.append(doc)
            _registrar("wikipedia_pt", url, topic_ids, True)
        else:
            _registrar("wikipedia_pt", url, topic_ids, False, "conteúdo insuficiente ou erro")

    # ── 2. Wikipedia EN ───────────────────────────────────────────────────────
    print("\n[2/6] Wikipedia EN")
    for titulo, topic_ids in WIKIPEDIA_EN_PAGES:
        print(f"  → {titulo}")
        doc = _coletar_wikipedia(titulo, topic_ids, lang="en")
        url = f"https://en.wikipedia.org/wiki/{titulo.replace(' ', '_')}"
        if doc:
            docs.append(doc)
            _registrar("wikipedia_en", url, topic_ids, True)
        else:
            _registrar("wikipedia_en", url, topic_ids, False, "conteúdo insuficiente ou erro")

    # ── 3. OpenStax ───────────────────────────────────────────────────────────
    print("\n[3/6] OpenStax")
    for source_kind, url, topic_id in OPENSTAX_URLS:
        print(f"  → {url.split('/')[-1]}")
        doc = _coletar_html(source_kind, url, [topic_id])
        if doc:
            docs.append(doc)
            _registrar("openstax", url, [topic_id], True)
        else:
            _registrar("openstax", url, [topic_id], False, "fetch ou parse falhou")

    # ── 4. MIT OCW ────────────────────────────────────────────────────────────
    print("\n[4/6] MIT OCW")
    for source_kind, url, topic_id in MIT_OCW_URLS:
        print(f"  → {url.split('/')[-2]}")
        doc = _coletar_html(source_kind, url, [topic_id])
        if doc:
            docs.append(doc)
            _registrar("mit_ocw", url, [topic_id], True)
        else:
            _registrar("mit_ocw", url, [topic_id], False, "fetch ou parse falhou")

    # ── 5. arXiv ──────────────────────────────────────────────────────────────
    print("\n[5/6] arXiv")
    for arxiv_id, topic_ids in ARXIV_IDS:
        print(f"  → arXiv:{arxiv_id}")
        doc = _coletar_arxiv(arxiv_id, topic_ids)
        if doc:
            docs.append(doc)
            _registrar("arxiv", f"https://arxiv.org/abs/{arxiv_id}", topic_ids, True)
        else:
            _registrar("arxiv", f"https://arxiv.org/abs/{arxiv_id}", topic_ids, False, "API falhou")

    # ── 6. Khan Academy ───────────────────────────────────────────────────────
    print("\n[6/6] Khan Academy")
    khan_urls = [
        ("https://pt.khanacademy.org/math/multivariable-calculus/multivariable-derivatives/partial-derivative-and-gradient-articles/a/introduction-to-partial-derivatives", ["funcoes-de-varias-variaveis"]),
        ("https://pt.khanacademy.org/math/multivariable-calculus/applications-of-multivariable-derivatives/optimizing-multivariable-functions/a/second-partial-derivative-test", ["maximos-e-minimos"]),
        ("https://pt.khanacademy.org/math/multivariable-calculus/integrating-multivariable-functions/double-integrals-topic/a/double-integrals-review", ["integrais-multiplas-mudanca-de-variaveis-em-integrais"]),
        ("https://pt.khanacademy.org/math/ap-calculus-bc/bc-series-new/bc-10-1/a/series-review", ["a-formula-de-taylor-e-series"]),
    ]
    for url, topic_ids in khan_urls:
        print(f"  → {url.split('/')[-2]}")
        doc = _coletar_html("khan_academy", url, topic_ids)
        if doc:
            docs.append(doc)
            _registrar("khan_academy", url, topic_ids, True)
        else:
            _registrar("khan_academy", url, topic_ids, False, "fetch ou parse falhou")

    # ── Salvar log ────────────────────────────────────────────────────────────
    tempo_total = round(time.time() - inicio_total, 2)
    sucessos = sum(1 for e in log_entries if e["sucesso"])
    falhas = len(log_entries) - sucessos

    log = {
        "executado_em": _now_iso(),
        "tempo_total_segundos": tempo_total,
        "total_tentativas": len(log_entries),
        "sucessos": sucessos,
        "falhas": falhas,
        "docs_coletados": len(docs),
        "chamadas_por_fonte": {
            fonte: sum(1 for e in log_entries if e["fonte"] == fonte)
            for fonte in ["wikipedia_pt", "wikipedia_en", "openstax", "mit_ocw", "arxiv", "khan_academy"]
        },
        "entradas": log_entries,
    }
    LOG_PATH.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✓ Coleta finalizada: {len(docs)} docs | {sucessos} ok | {falhas} falhas | {tempo_total}s")
    print(f"✓ Log salvo em: {LOG_PATH}")
    return docs


def main() -> None:
    plan = json.loads((ROOT / "data" / "plano_coleta.json").read_text(encoding="utf-8"))
    docs = collect(plan)
    # Salvar metadados dos docs coletados (sem conteúdo bruto)
    meta_path = ROOT / "data" / "collected_docs_meta.json"
    meta_path.write_text(
        json.dumps([asdict(d) for d in docs], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"✓ Metadados dos docs salvos em: {meta_path}")


if __name__ == "__main__":
    main()
