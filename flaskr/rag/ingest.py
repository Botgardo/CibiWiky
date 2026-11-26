"""Construye (o completa) la base vectorial de OWASP Top 10 2025.

Uso (desde la raíz del proyecto):
    python -m flaskr.rag.ingest            # solo añade las páginas que falten
    python -m flaskr.rag.ingest --reset    # borra todo y reconstruye
"""
import os
import re
import sys
import time
from urllib.parse import urljoin, urldefrag

import chromadb
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from google import genai
from google.genai import errors

load_dotenv(override=True)

INDEX_URL = os.getenv("OWASP_INDEX", "https://top10.owasp.org/2025/")
EMBED_MODEL = "gemini-embedding-001"
CHROMA_PATH = os.path.join(os.path.dirname(__file__), "chroma")
COLLECTION = "owasp2025"
CATEGORY_RE = re.compile(r"A(0[1-9]|10)[_:\-]", re.IGNORECASE)

BATCH = 20          # textos por petición
PAUSE = 13          # segundos entre lotes (~92 textos/min, bajo el límite de 100)
MAX_RETRIES = 5

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def fetch(url):
    r = requests.get(url, timeout=30, headers={"User-Agent": "cibiwiky-ingest/1.0"})
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def discover_urls():
    """Encuentra los enlaces A01..A10 desde la página índice (sin adivinar URLs)."""
    soup = fetch(INDEX_URL)
    urls = []
    for a in soup.find_all("a", href=True):
        href = urldefrag(urljoin(INDEX_URL, a["href"]))[0]
        if CATEGORY_RE.search(href) and href not in urls:
            urls.append(href)
    return urls


def clean_text(soup):
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    return re.sub(r"\s+", " ", main.get_text(" ")).strip()


def chunk(text, size=900, overlap=150):
    step = size - overlap
    return [text[i:i + size] for i in range(0, len(text), step)
            if text[i:i + size].strip()]


def embed_batch(texts, task):
    """Una petición con reintentos ante 429."""
    for attempt in range(MAX_RETRIES):
        try:
            r = client.models.embed_content(
                model=EMBED_MODEL, contents=texts,
                config={"task_type": task})
            return [e.values for e in r.embeddings]
        except errors.ClientError as e:
            if e.code != 429 or attempt == MAX_RETRIES - 1:
                raise
            wait = 40 + attempt * 20
            print(f"  límite de cuota, esperando {wait}s...")
            time.sleep(wait)


def embed(texts, task):
    out = []
    for i in range(0, len(texts), BATCH):
        out.extend(embed_batch(texts[i:i + BATCH], task))
        time.sleep(PAUSE)
    return out


def main():
    urls = discover_urls()
    if not urls:
        raise SystemExit(f"No se encontraron categorías en {INDEX_URL}. "
                         "Revisa OWASP_INDEX en .env")

    db = chromadb.PersistentClient(path=CHROMA_PATH)
    if "--reset" in sys.argv:
        try:
            db.delete_collection(COLLECTION)
        except Exception:
            pass
    col = db.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})

    for url in urls:
        if col.get(where={"url": url}, limit=1)["ids"]:
            print("ya existe, salto:", url)
            continue
        soup = fetch(url)
        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else url
        chunks = chunk(clean_text(soup))
        col.add(
            ids=[f"{url}#{i}" for i in range(len(chunks))],
            documents=chunks,
            embeddings=embed(chunks, "RETRIEVAL_DOCUMENT"),
            metadatas=[{"url": url, "title": title}] * len(chunks),
        )
        print(f"OK {title}: {len(chunks)} fragmentos")

    print("Total en la colección:", col.count())


if __name__ == "__main__":
    main()