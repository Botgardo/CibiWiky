"""Añade a la base vectorial el OWASP Cheat Sheet Series (soluciones y buenas prácticas).

Uso (desde la raíz del proyecto):
    python -m flaskr.rag.ingest_cheatsheets --dry-run   # cuenta fragmentos, sin gastar cuota
    python -m flaskr.rag.ingest_cheatsheets             # hojas ligadas al Top 10 (~44)
    python -m flaskr.rag.ingest_cheatsheets --all       # todas (~140, tarda bastante más)
    python -m flaskr.rag.ingest_cheatsheets --only SQL_Injection_Prevention_Cheat_Sheet

Es reanudable: salta las hojas que ya están indexadas. Se guardan en la misma
colección que el Top 10; el campo `kind` ("cheatsheet") las distingue.
"""
import re
import sys

import requests

RAW = "https://raw.githubusercontent.com/OWASP/CheatSheetSeries/master"
API_LIST = "https://api.github.com/repos/OWASP/CheatSheetSeries/contents/cheatsheets"
SITE = "https://cheatsheetseries.owasp.org/cheatsheets"

# Se omiten por defecto (con --all sí entran): listas de payloads/vocabulario que
# aportan poco a una respuesta y una hoja histórica.
SKIP_DEFAULT = {"XSS_Filter_Evasion_Cheat_Sheet.md",
                "Application_Logging_Vocabulary_Cheat_Sheet.md",
                "Abuse_Case_Cheat_Sheet.md"}

MAX_CHARS = 1400   # tamaño máximo de un fragmento
MIN_CHARS = 250    # secciones más cortas se pegan a la siguiente


def get(url, **kw):
    r = requests.get(url, timeout=30, headers={"User-Agent": "cibiwiky-ingest/1.0"}, **kw)
    r.raise_for_status()
    return r


def list_names(all_sheets):
    """Nombres de archivo .md. Por defecto, solo las hojas que OWASP liga al Top 10."""
    if all_sheets:
        return sorted(x["name"] for x in get(API_LIST).json() if x["name"].endswith(".md"))
    index = get(f"{RAW}/IndexTopTen.md").text
    return sorted(set(re.findall(r"\]\(cheatsheets/([^)]+\.md)\)", index)))


# ---------- Troceado por encabezados ----------
def split_sections(md):
    """[(ruta de encabezados, texto)] respetando los bloques de código."""
    sections, path, buf, in_code = [], [], [], False

    def flush():
        text = "\n".join(buf).strip()
        if text:
            sections.append((" > ".join(path), text))
        buf.clear()

    for line in md.splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
        m = None if in_code else re.match(r"^(#{1,4})\s+(.+?)\s*#*\s*$", line)
        if m:
            flush()
            level = len(m.group(1))
            path[:] = path[:level - 1] + [m.group(2).strip()]
        else:
            buf.append(line)
    flush()
    return sections


def blocks(text):
    """Párrafos y bloques de código completos."""
    out, cur, in_code = [], [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
            cur.append(line)
            if not in_code:
                out.append("\n".join(cur))
                cur = []
            continue
        if in_code:
            cur.append(line)
        elif not line.strip():
            if cur:
                out.append("\n".join(cur))
                cur = []
        else:
            cur.append(line)
    if cur:
        out.append("\n".join(cur))
    return out


def tidy(block):
    """Quita imágenes y deja solo el texto de los enlaces (no toca el código)."""
    if block.lstrip().startswith("```"):
        return block
    block = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", block)
    return re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", block).strip()


def hard_split(block, limit):
    out, cur = [], ""
    for line in block.splitlines():
        if cur and len(cur) + len(line) + 1 > limit:
            out.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        out.append(cur)
    return out


def pack(blks, limit):
    chunks, cur = [], ""
    for b in blks:
        for piece in ([b] if len(b) <= limit else hard_split(b, limit)):
            if cur and len(cur) + len(piece) + 2 > limit:
                chunks.append(cur)
                cur = piece
            else:
                cur = f"{cur}\n\n{piece}" if cur else piece
    if cur:
        chunks.append(cur)
    return chunks


def make_chunks(md):
    """Devuelve (título, [(sección, texto del fragmento)]). Cada fragmento lleva
    su ruta de encabezados al inicio para que el embedding sepa de qué trata."""
    sections = split_sections(md)
    title = sections[0][0].split(" > ")[0] if sections else ""
    out, pending = [], ""
    for path, text in sections:
        text = f"{pending}\n\n{text}".strip() if pending else text
        pending = ""
        if len(text) < MIN_CHARS:
            pending = f"{path}\n{text}"
            continue
        blks = [b for b in (tidy(b) for b in blocks(text)) if b]
        for piece in pack(blks, MAX_CHARS):
            out.append((path, f"{path}\n\n{piece}"))
    if pending:
        out.append(("", pending))
    return title, out


def main():
    argv = sys.argv[1:]
    dry = "--dry-run" in argv
    names = list_names("--all" in argv)
    if "--all" not in argv:
        names = [n for n in names if n not in SKIP_DEFAULT]
    if "--only" in argv:
        wanted = {n.removesuffix(".md") for n in argv[argv.index("--only") + 1:]}
        names = [n for n in names if n.removesuffix(".md") in wanted]
    if not names:
        raise SystemExit("No hay hojas que indexar.")

    col = embed = None
    if not dry:   # solo aquí se necesita GEMINI_API_KEY y ChromaDB
        import chromadb
        from flaskr.rag.ingest import CHROMA_PATH, COLLECTION, embed
        col = chromadb.PersistentClient(path=CHROMA_PATH).get_or_create_collection(
            COLLECTION, metadata={"hnsw:space": "cosine"})

    total = 0
    for name in names:
        stem = name.removesuffix(".md")
        url = f"{SITE}/{stem}.html"
        if col is not None and col.get(where={"url": url}, limit=1)["ids"]:
            print("ya existe, salto:", stem)
            continue
        title, chunks = make_chunks(get(f"{RAW}/cheatsheets/{name}").text)
        title = title or stem.replace("_", " ")
        total += len(chunks)
        if dry:
            print(f"{len(chunks):4d}  {title}")
            continue
        col.add(
            ids=[f"{url}#{i}" for i in range(len(chunks))],
            documents=[t for _, t in chunks],
            embeddings=embed([t for _, t in chunks], "RETRIEVAL_DOCUMENT"),
            metadatas=[{"url": url, "title": title, "kind": "cheatsheet",
                        "section": s} for s, _ in chunks],
        )
        print(f"OK {title}: {len(chunks)} fragmentos")

    if dry:
        mins = -(-total // 20) * 13 / 60
        print(f"\n{len(names)} hojas, {total} fragmentos (~{mins:.0f} min con el ritmo de ingest.py)")
    else:
        print("Total en la colección:", col.count())


if __name__ == "__main__":
    main()
