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

import json
import logging
import os
import sys
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

# Force UTF-8 output on Windows to prevent UnicodeEncodeError with emojis
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import chromadb
from chromadb.config import Settings
# Common chunker (shared with FTS5 and future BM25)
# pylint: disable=import-error
from chunking import chunk_text  # noqa: E402
from sentence_transformers import SentenceTransformer

# Cross-encoder reranker (optional module)
try:
    from l4_rerank import rerank as l4_rerank  # noqa: E402
except ImportError:
    l4_rerank = None

# ----------------------------
# CONFIG
# ----------------------------

DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"


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

        model_name = os.getenv("L4_MODEL", DEFAULT_MODEL)
        self.model = SentenceTransformer(model_name)

        self.collection_prefix = "memory_"
        self.global_collection = "memory_global"

    # =====================================================
    # EMBEDDING GATEWAY (P1)
    # =====================================================
    @lru_cache(maxsize=128)
    def _encode_query(self, query: str):
        """Возвращает embedding для запроса. Результат кэшируется."""
        result = self.model.encode([query])[0]
        return result.tolist() if hasattr(result, "tolist") else result

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

        Использует source и имя файла из metadata.
        """
        file = metadata.get("file", "unknown")
        normalized_source = source.replace("-", "_")
        return f"[{normalized_source}] {file}"

    # ----------------------------
    # MAIN SEARCH
    # ----------------------------

    # pylint: disable=too-many-branches, too-many-statements, too-many-locals
    def search_all(
        self, query: str, n_results: int = 10, enable_rerank: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Semantic cross-project search (hybrid-ready).
        Возвращает список результатов, каждый с ключом 'key' для RRF
        (document-level) и метаинформацией.

        Args:
            query: Search query
            n_results: Number of results to return
            enable_rerank: Apply cross-encoder reranking to results (default: False)
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

        # ------------------------
        # OPTIONAL RERANKING
        # ------------------------
        if enable_rerank and l4_rerank is not None and final:
            logging.info(
                "[RERANKING] Applying cross-encoder to %d semantic results...",
                len(final),
            )
            rerank_start = time.time()

            # Convert to RankedResult format for reranking
            from ranking import RankedResult  # noqa: E402

            candidates = []
            for result in final:
                candidates.append(
                    RankedResult(
                        key=result["key"],
                        score=1.0
                        / (1.0 + result["distance"]),  # Convert distance to score
                        sources={
                            "semantic": [
                                {
                                    "snippet": result["text"],
                                    "distance": result["distance"],
                                }
                            ]
                        },
                    )
                )

            # Apply reranking
            reranked = l4_rerank(query, candidates)

            # Convert back to dict format
            final_reranked = []
            for ranked in reranked:
                # Find original result by key
                orig = next((r for r in final if r["key"] == ranked.key), None)
                if orig:
                    result_dict = orig.copy()
                    result_dict["rerank_score"] = ranked.rerank_score
                    final_reranked.append(result_dict)

            final = final_reranked

            rerank_time = time.time() - rerank_start
            logging.info("[RERANKING] Completed in %.3fs", rerank_time)

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
            embeddings = []
            metadatas = []

            for i, chunk in enumerate(chunks):
                chunk_id = f"{md_file}:{i}"
                ids.append(chunk_id)
                documents.append(chunk)
                embeddings.append(self.model.encode([chunk])[0].tolist())
                metadatas.append(
                    {
                        "file": md_file.name,
                        "path": str(md_file),
                        "source": collection_name.replace(self.collection_prefix, ""),
                        "chunk_id": i,
                        "chunk_total": total,
                    }
                )

            collection.add(
                ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas
            )


# ----------------------------
# CLI
# ----------------------------


def main() -> None:
    mem = GlobalSemanticMemory()

    if len(sys.argv) < 3:
        print("Usage: l4_semantic_global.py <command> <query> [--json]")
        print("Commands: search, search-all")
        return

    cmd = sys.argv[1]

    # Проверка флага --json
    json_output = "--json" in sys.argv
    if json_output:
        sys.argv.remove("--json")

    query = " ".join(sys.argv[2:])

    if cmd in ("search", "search-all"):
        results = mem.search_all(query)

        if json_output:
            # JSON формат для RRF интеграции
            output = {
                "results": [
                    {
                        "key": r["key"],
                        "text": r["text"],
                        "distance": r["distance"],
                        "metadata": r["metadata"],
                        "source": r["source"],
                    }
                    for r in results
                ]
            }
            print(json.dumps(output, ensure_ascii=False))
        else:
            # Человекочитаемый формат
            for i, r in enumerate(results, 1):
                print(f"[{i}] {r['source']} | {r['metadata'].get('file')}")
                print(r["text"][:200])
                print("-" * 40)


if __name__ == "__main__":
    main()
