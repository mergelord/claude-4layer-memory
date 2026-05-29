#!/usr/bin/env python3
# pylint: disable=wrong-import-position, import-outside-toplevel
# -*- coding: utf-8 -*-
"""
L4 Semantic Global Memory Layer (Hybrid-ready)

Архитектура:
- ChromaDB semantic retrieval
- Global + multi-project memory
- RRF-ready fusion layer (BM25 future hook)
- Stable chunk-level dedup
- Embedding caching (LRU)
- Embedding Gateway (P1) – все поисковые запросы проходят через _encode_query
- Chunking contract: retrieval is chunk-level, fusion is document-level
"""

import codecs
import json
import logging
import os
import re
import sys
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

import chromadb
from chromadb.config import Settings

# Common chunker (shared with FTS5 and future BM25)
# pylint: disable=import-error
from chunking import chunk_text  # noqa: E402
from ranking import make_join_key, normalize_document_path  # noqa: E402

# ----------------------------
# CONFIG
# ----------------------------

DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
MAX_CHUNKS_PER_DOC = 3  # for future aggregation if needed
# Batch size for embedding encode calls during indexing. Larger batches
# improve throughput at the cost of memory; override via L4_EMBED_BATCH_SIZE.
EMBED_BATCH_SIZE = max(1, int(os.getenv("L4_EMBED_BATCH_SIZE", "64")))
_COLLECTION_NON_ALNUM = re.compile(r"[^a-zA-Z0-9_]")


def configure_utf8_output() -> None:
    """Force UTF-8 console output on Windows when the script runs as a CLI."""
    if sys.platform != "win32":
        return

    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        encoding = str(getattr(stream, "encoding", None) or "").lower()
        if encoding.replace("-", "") == "utf8":
            continue

        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="strict")
                continue
            except (AttributeError, OSError, ValueError):
                pass

        buffer = getattr(stream, "buffer", None)
        if buffer is not None:
            setattr(sys, stream_name, codecs.getwriter("utf-8")(buffer, "strict"))


# ----------------------------
# CORE CLASS
# ----------------------------


class GlobalSemanticMemory:
    """
    L4 semantic memory with hybrid-ready design.
    """

    # pylint: disable=too-many-instance-attributes

    def __init__(self) -> None:
        self.home = Path.home()

        self.global_memory = self.home / ".claude" / "memory"
        self.projects_base = self.home / ".claude" / "projects"

        self.db_path = self.home / ".claude" / "semantic_db_global"
        self.db_path.mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=str(self.db_path), settings=Settings(anonymized_telemetry=False)
        )

        self.model_name = os.getenv("L4_MODEL", DEFAULT_MODEL)
        self._model = None

        self.collection_prefix = "memory_"
        self.global_collection = "memory_global"

        # Per-instance query-embedding cache, created lazily on first use (see
        # _encode_query). Storing the lru_cache on the instance — instead of
        # decorating the method — keeps the cache scoped to this instance and
        # lets it be garbage-collected together with the instance. Decorating
        # an instance method with @lru_cache stores ``self`` in a cache that
        # lives on the class object, which pins every instance in memory and
        # shares cache entries across unrelated instances.
        self._encode_query_cache: Any = None

    @property
    def model(self):
        """Load SentenceTransformer only for operations that need embeddings."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                msg = (
                    "sentence_transformers is required for semantic search/index. "
                    "Install project dependencies and retry."
                )
                raise RuntimeError(msg) from exc
            self._model = SentenceTransformer(self.model_name)
        return self._model

    @model.setter
    def model(self, value) -> None:
        self._model = value

    # =====================================================
    # EMBEDDING GATEWAY (P1)
    # =====================================================
    def _encode_query(self, query: str):
        """Возвращает embedding для запроса (per-instance LRU-кэш).

        Кэш создаётся лениво при первом вызове и хранится на экземпляре
        (``self._encode_query_cache``), поэтому собирается GC вместе с
        экземпляром и не шарится между разными экземплярами. Работает и для
        экземпляров, созданных в обход ``__init__`` (например, через ``__new__``
        в тестах).
        """
        cache = getattr(self, "_encode_query_cache", None)
        if cache is None:
            cache = lru_cache(maxsize=128)(self._encode_query_impl)
            self._encode_query_cache = cache
        return cache(query)

    def _encode_query_impl(self, query: str):
        """Реальная реализация encode (вызывается через self._encode_query)."""
        result = self.model.encode([query])[0]
        return result.tolist() if hasattr(result, "tolist") else result

    def _encode_documents(self, documents: List[str]) -> List[Any]:
        """Batch-encode chunk documents into embedding vectors.

        Все чанки кодируются одним батч-вызовом ``model.encode`` вместо
        отдельного вызова на каждый чанк — это убирает основную стоимость
        индексации больших директорий.

        Возвращает список float-векторов (по одному на чанк). Тип элемента
        намеренно оставлен ``Any``: ``list`` в mypy инвариантен, и более точный
        ``List[List[float]]`` не принимается ``Collection.upsert(embeddings=...)``,
        который ждёт ``list[Sequence[float] | Sequence[int]]``.
        """
        if not documents:
            return []
        encoded = self.model.encode(documents, batch_size=EMBED_BATCH_SIZE)
        if hasattr(encoded, "tolist"):
            return encoded.tolist()
        return [
            vec.tolist() if hasattr(vec, "tolist") else list(vec) for vec in encoded
        ]

    # ----------------------------
    # COLLECTIONS
    # ----------------------------

    def _get_collection(self, name: str):
        """Безопасное получение коллекции с логированием ошибок."""
        try:
            return self.client.get_collection(name)
        except Exception as e:  # nosec
            logging.error("Failed to get collection %s: %s", name, e)
            return None

    def _normalize_collection_suffix(self, project_name: str) -> str:
        """Return the Chroma-compatible project suffix used in collection names."""
        return _COLLECTION_NON_ALNUM.sub("_", project_name)

    def _resolve_project_collection_name(self, project_name: str) -> str:
        """Resolve a user project argument to an existing Chroma collection name."""
        normalized_suffix = self._normalize_collection_suffix(project_name)
        candidate = self.collection_prefix + normalized_suffix

        if self._get_collection(candidate) is not None:
            return candidate

        prefix = self.collection_prefix + normalized_suffix
        matches = sorted(
            c.name
            for c in self.client.list_collections()
            if c.name.startswith(prefix) and c.name != self.global_collection
        )
        return matches[0] if matches else candidate

    # ----------------------------
    # SEARCH CORE
    # ----------------------------

    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def _search_collection(
        self, collection, embedding: List[float], limit: int, source: str
    ) -> List[Dict[str, Any]]:
        """Поиск по одной коллекции. Возвращает чанки с метаданными."""

        if not collection:
            return []

        res = collection.query(query_embeddings=[embedding], n_results=limit)

        out: List[Dict[str, Any]] = []

        if not res.get("ids"):
            return out

        ids = res["ids"][0]
        docs = res["documents"][0]
        metas = res["metadatas"][0]
        dists = res.get("distances", [[]])[0]

        for i, id_val in enumerate(ids):
            metadata = metas[i] if i < len(metas) else {}
            out.append(
                {
                    "id": id_val,
                    "key": self._make_document_key(source, metadata),
                    "text": docs[i],
                    "metadata": metadata,
                    "distance": dists[i] if i < len(dists) else 999,
                    "source": source,
                }
            )

        return out

    # ----------------------------
    # ADAPTER: chunk -> document key (для RRF)
    # ----------------------------

    def _make_document_key(self, source: str, metadata: Dict[str, Any]) -> str:
        """
        Формирует document-level ключ для RRF на основе метаданных чанка.

        Нормализация делегирована :func:`ranking.make_join_key`, чтобы semantic /
        BM25 / FTS5 все сходились на один и тот же ключ для одного документа.
        """
        file = metadata.get("file", "unknown")
        return make_join_key(source, file)

    # ----------------------------
    # MAIN SEARCH
    # ----------------------------

    # pylint: disable=too-many-branches, too-many-statements, too-many-locals
    def search_all(
        self, query: str, n_results: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Semantic cross-project search (hybrid-ready).
        Возвращает список результатов, каждый с ключом 'key' для RRF
        (document-level) и метаинформацией.

        Args:
            query: Search query
            n_results: Number of results to return

        Note:
            Cross-encoder reranking is **not** applied here.
            ``l4_rerank.rerank`` operates on the merged ``RankedResult``
            objects produced by :func:`ranking.rrf_merge`, so reranking
            is the hybrid layer's responsibility (see
            ``l4_fts5_search.cmd_hybrid`` and ``cmd_hybrid_parallel``).
            Calling ``rerank`` on this function's dict output would be
            a contract violation.
        """
        start_time = time.time()
        embedding = self._encode_query(query)

        results_by_source: Dict[str, List[Dict[str, Any]]] = {"semantic": []}

        # ------------------------
        # GLOBAL MEMORY
        # ------------------------

        try:
            global_col = self._get_collection(self.global_collection)

            results_by_source["semantic"].extend(
                self._search_collection(global_col, embedding, n_results, "global")
            )
        except Exception:  # nosec
            pass

        # ------------------------
        # PROJECTS
        # ------------------------

        prefix = self.collection_prefix
        collections = self.client.list_collections()

        project_cols = [
            c
            for c in collections
            if c.name.startswith(prefix) and c.name != self.global_collection
        ]

        per_col = max(n_results, 10)

        for c in project_cols:
            try:
                col = self._get_collection(c.name)
                project_name = c.name[len(prefix) :]

                results_by_source["semantic"].extend(
                    self._search_collection(col, embedding, per_col, project_name)
                )
            except Exception:  # nosec
                continue

        # ------------------------
        # LOCAL RANKING (within semantic)
        # ------------------------

        for _, results in results_by_source.items():
            results.sort(key=lambda x: (x["distance"], x["id"]))
            for i, r in enumerate(results):
                r["_rank"] = i + 1

        # ------------------------
        # ADAPTER LAYER: chunk -> document для RRF
        # ------------------------

        semantic_docs: Dict[str, Dict[str, Any]] = {}
        for chunk in results_by_source["semantic"]:
            doc_key = self._make_document_key(chunk["source"], chunk["metadata"])
            if doc_key not in semantic_docs:
                semantic_docs[doc_key] = {
                    "key": doc_key,
                    "best_chunk": chunk,
                    "distance": chunk["distance"],
                    "chunks": [chunk],
                }
            else:
                if chunk["distance"] < semantic_docs[doc_key]["distance"]:
                    semantic_docs[doc_key]["best_chunk"] = chunk
                    semantic_docs[doc_key]["distance"] = chunk["distance"]
                semantic_docs[doc_key]["chunks"].append(chunk)

        sorted_docs = sorted(semantic_docs.values(), key=lambda x: x["distance"])[
            :n_results
        ]

        final = []
        for doc in sorted_docs:
            best = doc["best_chunk"]
            final.append(
                {
                    "id": best["id"],
                    "key": doc["key"],
                    "text": best["text"],
                    "distance": doc["distance"],
                    "metadata": best["metadata"],
                    "source": best["source"],
                    "_chunks": doc["chunks"],
                }
            )

        elapsed = time.time() - start_time
        logging.info(
            "Search completed in %.2f seconds, %d results", elapsed, len(final)
        )

        return final

    # ----------------------------
    # RRF STUB (future BM25)
    # ----------------------------

    def _rrf_stub(self, sources: Dict[str, List[Dict[str, Any]]]):
        """Placeholder for real RRF fusion."""
        merged = []
        for _, items in sources.items():
            merged.extend(items)
        return merged

    # ----------------------------
    # INDEXING (with chunking)
    # ----------------------------

    def index_directory(self, path: Path, collection_name: str) -> None:
        """
        Индексирует все markdown файлы в директории, разбивая их на чанки.

        Для каждого файла создаётся несколько чанков с одинаковым `file` и `source`,
        но уникальным `chunk_id`. Идентификатор в ChromaDB: ``<file_path>:<chunk_id>``.

        Эмбеддинги для всех чанков файла считаются одним батч-вызовом
        (см. :meth:`_encode_documents`), а не по одному чанку за раз.
        """
        if not path.exists():
            return

        collection = self.client.get_or_create_collection(collection_name)

        for md_file in path.rglob("*.md"):
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:  # nosec
                continue

            chunks = chunk_text(text)
            total = len(chunks)
            if total == 0:
                continue

            ids = []
            documents = []
            metadatas = []

            for i, chunk in enumerate(chunks):
                chunk_id = f"{md_file}:{i}"
                ids.append(chunk_id)
                documents.append(chunk)
                metadatas.append(
                    {
                        "file": normalize_document_path(md_file.relative_to(path)),
                        "path": str(md_file),
                        "source": collection_name.replace(self.collection_prefix, ""),
                        "chunk_id": i,
                        "chunk_total": total,
                    }
                )

            # Batch-encode all chunks of this file in a single model call.
            embeddings = self._encode_documents(documents)

            collection.upsert(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,  # type: ignore[arg-type]
            )


# ----------------------------
# CLI METHODS
# ----------------------------

    def index_all(self) -> None:
        """Индексирует глобальную память и все проекты."""
        self.index_directory(self.global_memory, self.global_collection)
        print(f"[OK] Indexed global: {self.global_memory}")

        if self.projects_base.exists():
            for project_dir in sorted(self.projects_base.iterdir()):
                if not project_dir.is_dir():
                    continue
                memory_dir = project_dir / "memory"
                if memory_dir.exists():
                    col_name = self.collection_prefix + project_dir.name
                    self.index_directory(memory_dir, col_name)
                    print(f"[OK] Indexed project: {project_dir.name}")

    def print_stats(self) -> None:
        """Выводит статистику по коллекциям ChromaDB."""
        collections = self.client.list_collections()
        print(f"DB: {self.db_path}")
        print(f"Collections: {len(collections)}")
        for c in collections:
            col = self.client.get_collection(c.name)
            print(f"  {c.name}: {col.count()} documents")

    def cleanup(self, dry_run: bool = False) -> None:
        """Удаляет пустые коллекции."""
        collections = self.client.list_collections()
        removed = 0
        for c in collections:
            col = self.client.get_collection(c.name)
            if col.count() == 0:
                if dry_run:
                    print(f"[DRY-RUN] Would remove: {c.name}")
                else:
                    self.client.delete_collection(c.name)
                removed += 1
        action = "Would remove" if dry_run else "Removed"
        print(f"[OK] {action} {removed} empty collections")

    def search_global(self, query: str, n_results: int = 10) -> List[Dict[str, Any]]:
        """Поиск только в глобальной памяти."""
        embedding = self._encode_query(query)
        col = self._get_collection(self.global_collection)
        return self._search_collection(col, embedding, n_results, "global")

    def search_project(self, project_name: str, query: str, n_results: int = 10) -> List[Dict[str, Any]]:
        """Поиск только в памяти конкретного проекта."""
        embedding = self._encode_query(query)
        col_name = self._resolve_project_collection_name(project_name)
        col = self._get_collection(col_name)
        source = col_name[len(self.collection_prefix) :]
        return self._search_collection(col, embedding, n_results, source)


# ----------------------------
# CLI
# ----------------------------

COMMANDS_HELP = (
    "Commands: search, search-all, search-global, search-project, "
    "index-all, stats, cleanup"
)


def _print_usage() -> None:
    print("Usage: l4_semantic_global.py <command> [args] [--json]")
    print(COMMANDS_HELP)


def _run_admin_command(mem: GlobalSemanticMemory, cmd: str) -> bool:
    """Run non-search CLI commands. Returns True when command was handled."""
    if cmd in ("index-all", "reindex"):
        mem.index_all()
        return True

    if cmd == "stats":
        mem.print_stats()
        return True

    if cmd == "cleanup":
        dry_run = "--dry-run" in sys.argv
        mem.cleanup(dry_run=dry_run)
        return True

    return False


def _get_search_results(
    mem: GlobalSemanticMemory, cmd: str
) -> List[Dict[str, Any]] | None:
    """Dispatch search commands and return None for invalid commands/arguments."""
    results: List[Dict[str, Any]] | None = None

    if cmd in ("search", "search-all"):
        if len(sys.argv) < 3:
            print(f"Usage: l4_semantic_global.py {cmd} <query>")
        else:
            query = " ".join(sys.argv[2:])
            results = mem.search_all(query)

    elif cmd == "search-global":
        if len(sys.argv) < 3:
            print("Usage: l4_semantic_global.py search-global <query>")
        else:
            query = " ".join(sys.argv[2:])
            results = mem.search_global(query)

    elif cmd == "search-project":
        if len(sys.argv) < 4:
            print("Usage: l4_semantic_global.py search-project <project> <query>")
        else:
            project = sys.argv[2]
            query = " ".join(sys.argv[3:])
            results = mem.search_project(project, query)

    else:
        print(f"Unknown command: {cmd}")
        print(COMMANDS_HELP)

    return results


def _print_results(results: List[Dict[str, Any]], json_output: bool) -> None:
    if json_output:
        output = {
            "results": [
                {
                    "key": r.get(
                        "key",
                        make_join_key(r["source"], r["metadata"].get("file", "unknown")),
                    ),
                    "text": r["text"],
                    "distance": r["distance"],
                    "metadata": r["metadata"],
                    "source": r["source"],
                }
                for r in results
            ]
        }
        print(json.dumps(output, ensure_ascii=False))
        return

    if results:
        print("[SEARCH ALL]")
    for i, r in enumerate(results, 1):
        print(f"[{i}] {r['source']} | {r['metadata'].get('file')}")
        print(r["text"][:200])
        print("-" * 40)


def main() -> None:
    configure_utf8_output()
    mem = GlobalSemanticMemory()

    if len(sys.argv) < 2:
        _print_usage()
        return

    cmd = sys.argv[1]

    # Проверка флага --json
    json_output = "--json" in sys.argv
    if json_output:
        sys.argv.remove("--json")

    if _run_admin_command(mem, cmd):
        return

    results = _get_search_results(mem, cmd)
    if results is None:
        return

    _print_results(results, json_output)


if __name__ == "__main__":
    main()
