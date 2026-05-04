#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
L4 Semantic Global Memory Layer (Hybrid-ready)

Архитектура:
- ChromaDB semantic retrieval
- Global + multi-project memory
- RRF-ready fusion layer (BM25 future hook)
- Stable chunk-level dedup
- Embedding caching (LRU)
"""

import os
import sys
import time
import logging
from pathlib import Path
from typing import List, Dict, Any
from functools import lru_cache

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer


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

    def __init__(self):
        self.home = Path.home()

        self.global_memory = self.home / ".claude" / "memory"
        self.projects_base = self.home / ".claude" / "projects"

        self.db_path = self.home / ".claude" / "semantic_db_global"
        self.db_path.mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=str(self.db_path),
            settings=Settings(anonymized_telemetry=False)
        )

        model_name = os.getenv("L4_MODEL", DEFAULT_MODEL)
        self.model = SentenceTransformer(model_name)

        self.collection_prefix = "memory_"
        self.global_collection = "memory_global"

    # ----------------------------
    # EMBEDDINGS (with cache)
    # ----------------------------

    @lru_cache(maxsize=128)
    def _encode(self, text: str):
        """Возвращает embedding для запроса. Результат кэшируется."""
        emb = self.model.encode([text])[0]
        return emb.tolist() if hasattr(emb, "tolist") else emb

    # ----------------------------
    # COLLECTIONS
    # ----------------------------

    def _get_collection(self, name: str):
        """Безопасное получение коллекции с логированием ошибок."""
        try:
            return self.client.get_collection(name)
        except Exception as e:
            logging.error("Failed to get collection %s: %s", name, e)
            return None

    # ----------------------------
    # SEARCH CORE
    # ----------------------------

    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def _search_collection(
        self,
        collection,
        embedding: List[float],
        limit: int,
        source: str
    ) -> List[Dict[str, Any]]:
        """Поиск по одной коллекции."""

        if not collection:
            return []

        res = collection.query(
            query_embeddings=[embedding],
            n_results=limit
        )

        out = []

        if not res.get("ids"):
            return out

        ids = res["ids"][0]
        docs = res["documents"][0]
        metas = res["metadatas"][0]
        dists = res.get("distances", [[]])[0]

        for i, id_val in enumerate(ids):
            out.append({
                "id": id_val,
                "text": docs[i],
                "metadata": metas[i],
                "distance": dists[i] if i < len(dists) else 999,
                "source": source
            })

        return out

    # ----------------------------
    # MAIN SEARCH
    # ----------------------------

    def search_all(self, query: str, n_results: int = 10) -> List[Dict[str, Any]]:
        """
        Semantic cross-project search (hybrid-ready).
        """
        # pylint: disable=too-many-locals
        start_time = time.time()
        embedding = self._encode(query)

        results_by_source: Dict[str, List[Dict[str, Any]]] = {
            "semantic": []
        }

        # ------------------------
        # GLOBAL MEMORY
        # ------------------------

        try:
            global_col = self._get_collection(self.global_collection)

            results_by_source["semantic"].extend(
                self._search_collection(
                    global_col,
                    embedding,
                    n_results,
                    "global"
                )
            )
        except Exception:
            pass

        # ------------------------
        # PROJECTS
        # ------------------------

        prefix = self.collection_prefix
        collections = self.client.list_collections()

        project_cols = [
            c for c in collections
            if c.name.startswith(prefix) and c.name != self.global_collection
        ]

        # oversample (important for recall)
        per_col = max(n_results, 10)

        for c in project_cols:
            try:
                col = self._get_collection(c.name)
                project_name = c.name[len(prefix):]

                results_by_source["semantic"].extend(
                    self._search_collection(
                        col,
                        embedding,
                        per_col,
                        project_name
                    )
                )
            except Exception:
                continue

        # ------------------------
        # LOCAL RANKING
        # ------------------------

        for _, results in results_by_source.items():
            results.sort(key=lambda x: (x["distance"], x["id"]))
            for i, r in enumerate(results):
                r["_rank"] = i + 1

        # ------------------------
        # HYBRID HOOK (future BM25)
        # ------------------------

        active_sources = {
            k: v for k, v in results_by_source.items() if v
        }

        if len(active_sources) > 1:
            # future:
            # return rrf_merge(active_sources, k=60)
            merged = self._rrf_stub(active_sources)
        else:
            merged = sorted(
                results_by_source["semantic"],
                key=lambda x: x["_rank"]
            )

        # ------------------------
        # DEDUP (chunk-level safe)
        # ------------------------

        best = {}

        for r in merged:
            key = r["id"]

            if key not in best:
                best[key] = r
            else:
                # prefer better semantic rank
                if r["_rank"] < best[key]["_rank"]:
                    best[key] = r

        final = list(best.values())

        # cleanup
        for r in final:
            r.pop("_rank", None)

        elapsed = time.time() - start_time
        logging.info("Search completed in %.2f seconds, %d results",
                     elapsed, len(final))

        return final[:n_results]

    # ----------------------------
    # RRF STUB (future BM25)
    # ----------------------------

    def _rrf_stub(self, sources: Dict[str, List[Dict[str, Any]]]):
        """
        Placeholder for real RRF fusion.
        Пока просто объединяет отсортированные списки без повторной сортировки.
        """
        merged = []

        for _, items in sources.items():
            merged.extend(items)

        # Уже отсортированы по рангу внутри каждого источника,
        # поэтому просто возвращаем как есть.
        return merged

    # ----------------------------
    # INDEXING (minimal version)
    # ----------------------------

    def index_directory(self, path: Path, collection_name: str):
        if not path.exists():
            return

        collection = self.client.get_or_create_collection(collection_name)

        files = list(path.rglob("*.md"))

        texts = []
        ids = []
        metas = []

        for f in files:
            try:
                text = f.read_text(encoding="utf-8")
            except Exception:
                continue

            texts.append(text)
            ids.append(str(f))

            metas.append({
                "file": f.name,
                "path": str(f)
            })

        if not texts:
            return

        embeddings = self.model.encode(texts).tolist()

        collection.add(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metas
        )


# ----------------------------
# CLI
# ----------------------------

def main():
    mem = GlobalSemanticMemory()

    if len(sys.argv) < 3:
        print("Usage: search_all <query>")
        return

    cmd = sys.argv[1]
    query = " ".join(sys.argv[2:])

    if cmd == "search":
        results = mem.search_all(query)

        for i, r in enumerate(results, 1):
            print(f"[{i}] {r['source']} | {r['metadata'].get('file')}")
            print(r["text"][:200])
            print("-" * 40)


if __name__ == "__main__":
    main()