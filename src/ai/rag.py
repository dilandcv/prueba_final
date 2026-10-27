"""Módulo RAG ligero para indexación y recuperación documental técnica en PostgreSQL."""
from pathlib import Path
import re
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

DOC_SOURCES = [
    ("README", PROJECT_ROOT / "README.md"),
    ("Arquitectura", PROJECT_ROOT / "docs" / "ARQUITECTURA.md"),
    ("Modelo de Datos", PROJECT_ROOT / "docs" / "MODELO_DATOS.md"),
    ("Gobernanza y OpenMetadata", PROJECT_ROOT / "docs" / "GOBERNANZA_OPENMETADATA.md"),
]


def chunk_markdown_file(doc_name: str, file_path: Path) -> list[dict[str, str]]:
    """Divide un archivo Markdown en fragmentos coherentes delimitados por encabezados ## y ###."""
    if not file_path.exists():
        return []

    text = file_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    chunks: list[dict[str, str]] = []
    current_title = doc_name
    current_lines: list[str] = []

    for line in lines:
        if line.startswith("## ") or line.startswith("### "):
            if current_lines:
                chunk_body = "\n".join(current_lines).strip()
                if len(chunk_body) > 30:
                    chunks.append({
                        "doc_name": doc_name,
                        "section_title": current_title,
                        "file_path": str(file_path),
                        "content": chunk_body,
                    })
                current_lines = []
            current_title = line.lstrip("#").strip()
        else:
            current_lines.append(line)

    if current_lines:
        chunk_body = "\n".join(current_lines).strip()
        if len(chunk_body) > 30:
            chunks.append({
                "doc_name": doc_name,
                "section_title": current_title,
                "file_path": str(file_path),
                "content": chunk_body,
            })

    return chunks


def index_all_documents(conn) -> int:
    """Indexa o actualiza todos los documentos técnicos del proyecto en ops.project_documents."""
    all_chunks = []
    for doc_name, path in DOC_SOURCES:
        all_chunks.extend(chunk_markdown_file(doc_name, path))

    if not all_chunks:
        return 0

    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE ops.project_documents;")
        insert_sql = """
            INSERT INTO ops.project_documents (doc_name, section_title, file_path, content)
            VALUES (%s, %s, %s, %s);
        """
        for ch in all_chunks:
            cur.execute(insert_sql, (ch["doc_name"], ch["section_title"], ch["file_path"], ch["content"]))
        conn.commit()

    return len(all_chunks)


def search_project_documentation(cur, query: str, limit: int = 4) -> list[dict[str, Any]]:
    """Busca fragmentos relevantes usando búsqueda de texto completo (FTS) e ILIKE en PostgreSQL."""
    clean_query = query.strip()
    if not clean_query:
        return []

    # Filtrado de palabras vacías y construcción de consulta OR para máxima cobertura
    stopwords = {
        "de", "la", "el", "los", "las", "un", "una", "unos", "unas", "y", "o", "en", "a", "por",
        "para", "con", "que", "qué", "cual", "cuáles", "cuales", "como", "cómo", "es", "son",
        "se", "su", "sus", "al", "del", "este", "esta", "estos", "estas", "tiene", "durante",
        "entre", "sobre", "antes", "después", "desde", "hasta", "cada", "todo", "toda"
    }
    raw_tokens = [re.sub(r"[^\w]", "", t.lower()) for t in clean_query.split()]
    meaningful_tokens = [t for t in raw_tokens if len(t) >= 3 and t not in stopwords]

    # Construir consulta OR con websearch_to_tsquery
    search_expr = " OR ".join(meaningful_tokens) if meaningful_tokens else clean_query

    # 1. Búsqueda por FTS con ranking y operadores OR
    fts_sql = """
        SELECT
            doc_name,
            section_title,
            file_path,
            content,
            ts_rank(tsv, websearch_to_tsquery('spanish', %s)) AS rank
        FROM ops.project_documents
        WHERE tsv @@ websearch_to_tsquery('spanish', %s)
        ORDER BY rank DESC
        LIMIT %s;
    """
    cur.execute(fts_sql, (search_expr, search_expr, limit))
    rows = cur.fetchall()

    results = []
    for r in rows:
        results.append({
            "doc_name": r[0],
            "section_title": r[1],
            "file_path": r[2],
            "content": r[3],
            "relevance": float(r[4]),
        })

    # 2. Si FTS no arrojó resultados (ej. palabras técnicas en inglés como 'spark', 'fastapi', 'airflow'):
    if not results:
        terms = [t for t in re.split(r"\W+", clean_query) if len(t) > 3]
        if terms:
            like_clauses = " OR ".join(["content ILIKE %s" for _ in terms])
            like_params = [f"%{t}%" for t in terms]
            fallback_sql = f"""
                SELECT doc_name, section_title, file_path, content, 0.5 AS rank
                FROM ops.project_documents
                WHERE {like_clauses}
                LIMIT %s;
            """
            cur.execute(fallback_sql, (*like_params, limit))
            for r in cur.fetchall():
                results.append({
                    "doc_name": r[0],
                    "section_title": r[1],
                    "file_path": r[2],
                    "content": r[3],
                    "relevance": float(r[4]),
                })

    return results
