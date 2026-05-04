#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# pylint: disable=too-many-lines
r"""
L4 SEMANTIC Memory Layer - Cross-Project Search

Расширенная версия с поддержкой:
- Глобальной памяти (~/.claude/memory/)
- Кросс-проектного поиска (по всем проектам)
- Поиска только в глобальной памяти
- Поиска только в конкретном проекте
- Whitelist фильтрации проектов
- Очистки мусорных коллекций

Требования:
    pip install chromadb sentence-transformers

Использование:
    # Индексировать глобальную память
    python l4_semantic_global.py index-global

    # Индексировать проект
    python l4_semantic_global.py index-project <project-path>

    # Индексировать всё (глобальная + whitelist проекты)
    python l4_semantic_global.py index-all

    # Поиск везде (глобальная + все проекты)
    python l4_semantic_global.py search-all "query"

    # Поиск только в глобальной памяти
    python l4_semantic_global.py search-global "query"

    # Поиск только в проекте
    python l4_semantic_global.py search-project <project-path> "query"

    # Статистика
    python l4_semantic_global.py stats

    # Очистка мусорных коллекций (dry-run)
    python l4_semantic_global.py cleanup --dry-run

    # Очистка мусорных коллекций (реальное удаление)
    python l4_semantic_global.py cleanup

Переменные окружения:
    L4_MODEL - модель для эмбеддингов (по умолчанию: paraphrase-multilingual-MiniLM-L12-v2)
    Пример: export L4_MODEL=all-MiniLM-L6-v2
"""

import hashlib
import json
import logging
import os
import re
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# Настройка UTF-8 для Windows консоли
# NOTE: Необходимо для корректного отображения русского текста в Windows cmd/PowerShell
# Python 3.7+ поддерживает UTF-8, но Windows консоль требует явной настройки
# Альтернатива: установить environment variable PYTHONIOENCODING=utf-8
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

try:
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer
except ImportError:
    print("ERROR: Required packages not installed")
    print("Run: pip install chromadb sentence-transformers")
    sys.exit(1)


class GlobalSemanticMemory:
    """L4 SEMANTIC с поддержкой глобальной памяти и кросс-проектного поиска"""

    DEFAULT_CONFIG = {
        'embedding_model': 'paraphrase-multilingual-MiniLM-L12-v2',
        'batch_size': 10,
        'max_workers': 4,
        'max_chunk_size': 500,
        'search_results': {'default': 10, 'global': 5, 'project': 5},
        'cache_size': 128,
        'collection_names': {'global': 'memory_global', 'project_prefix': 'memory_'}
    }

    @staticmethod
    def normalize_project_name(name: str) -> str:
        """
        Нормализация имён проектов для использования в качестве имён коллекций.

        Заменяет дефисы, пробелы и другие спецсимволы на подчёркивания.
        Схлопывает множественные подчёркивания в одно.
        ChromaDB требует имена коллекций без спецсимволов.

        Args:
            name: Исходное имя проекта

        Returns:
            Нормализованное имя (только буквы, цифры, подчёркивания)

        Example:
            >>> normalize_project_name("my-project-name")
            'my_project_name'
            >>> normalize_project_name("project with spaces")
            'project_with_spaces'
            >>> normalize_project_name("my--weird__project")
            'my_weird_project'
        """
        # Заменяем спецсимволы на подчёркивания
        normalized = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        # Схлопываем множественные подчёркивания в одно
        normalized = re.sub(r'_+', '_', normalized)
        return normalized

    @staticmethod
    def _normalize_id_part(text: str) -> str:
        """Build an ASCII-safe component for ChromaDB chunk IDs.

        Non-ASCII names (e.g. ``тест.md``) would otherwise produce IDs that
        break round-tripping through some Chroma backends and confuse the
        ``where`` filters in ``_add_batch_to_collection``. We:

        1. NFKD-normalize and ASCII-encode to drop diacritics where possible,
        2. Replace any remaining non-``[A-Za-z0-9._-]`` characters with ``_``,
        3. Append a short stable hash whenever lossy conversion happened
           (so ``файл-один`` and ``файл-два`` don't collapse to the same
           ASCII residue) — and use the hash on its own when everything
           was stripped.
        """
        decomposed = unicodedata.normalize('NFKD', text)
        ascii_only = decomposed.encode('ascii', 'ignore').decode('ascii')
        safe = re.sub(r'[^A-Za-z0-9._-]', '_', ascii_only).strip('_-')

        # Detect lossy conversion by comparing the two residues *as
        # strings*, not by length. Equal lengths can still mean lossy
        # conversion: ``naïve`` NFKD-decomposes to ``n a i + combining
        # diaeresis + v e``, the combining mark is dropped by ASCII
        # encoding so ``safe`` becomes ``naive`` (length 5), while the
        # original-text regex turns ``naïve`` into ``na_ve`` (length 5
        # too) — a length-only check would miss the collision and emit
        # the same chunk ID for ``naive`` and ``naïve``.
        original_safe = re.sub(r'[^A-Za-z0-9._-]', '_', text).strip('_-')
        lost_information = original_safe != safe

        # MD5 here is a non-cryptographic ID derivation (collision-resistance,
        # not security), so we pass usedforsecurity=False to satisfy bandit/B324.
        if not safe:
            return hashlib.md5(  # nosec B324 - non-security collision check
                text.encode('utf-8'), usedforsecurity=False
            ).hexdigest()[:12]
        if lost_information:
            short_hash = hashlib.md5(  # nosec B324 - non-security collision check
                text.encode('utf-8'), usedforsecurity=False
            ).hexdigest()[:8]
            return f"{safe}_{short_hash}"
        return safe

    def __init__(self):
        """Инициализация с автоопределением путей"""
        self.home = Path.home()
        self.global_memory = self.home / ".claude" / "memory"
        self.projects_base = self.home / ".claude" / "projects"
        self.global_projects_file = self.home / ".claude" / "GLOBAL_PROJECTS.md"

        # Загрузка конфигурации
        self.config = self._load_config()

        # Валидация путей
        self._validate_paths()

        # Автоопределение проектов
        self.project_whitelist = self._discover_projects()

        # Единая БД для всех коллекций
        self.db_path = self.home / ".claude" / "semantic_db_global"
        self.db_path.mkdir(parents=True, exist_ok=True)

        # Инициализация ChromaDB
        self.client = chromadb.PersistentClient(
            path=str(self.db_path),
            settings=Settings(anonymized_telemetry=False)
        )

        # Модель для эмбеддингов (мультиязычная)
        model_name = os.getenv('L4_MODEL', self.config['embedding_model'])
        logging.info("Loading embedding model: %s", model_name)
        self.model = SentenceTransformer(model_name)

    def _load_config(self) -> Dict[str, Any]:
        """Загрузка конфигурации из JSON или использование defaults.

        Catches only the specific JSON / I/O error families instead of bare
        ``Exception``: a malformed or unreadable config file should fall
        back to defaults, but a programming bug elsewhere (e.g. ``TypeError``
        in ``json.load``) should still surface as a hard failure.
        """
        config_file = Path(__file__).parent.parent / "config" / "semantic_config.json"

        if config_file.exists() and os.access(config_file, os.R_OK):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
                logging.warning("Failed to load semantic_config.json: %s", e)
                logging.warning("Using default configuration")

        return self.DEFAULT_CONFIG

    def _validate_paths(self):
        """Валидация критических путей"""
        try:
            home_resolved = self.home.resolve()

            # Проверяем что все пути внутри home
            for path in [self.global_memory, self.projects_base, self.global_projects_file]:
                resolved = path.resolve()
                if not str(resolved).startswith(str(home_resolved)):
                    raise ValueError(f"Path outside home directory: {path}")
        except Exception as exc:
            raise ValueError(f"Path validation failed: {exc}") from exc

    def _discover_projects(self) -> list:
        """Автоматическое определение проектов

        Комбо-подход:
        1. Парсинг GLOBAL_PROJECTS.md (основной источник)
        2. Fallback: автоопределение по наличию CLAUDE.md (только если GLOBAL_PROJECTS.md не найден)

        Returns:
            Список имён директорий проектов
        """
        projects = set()

        # Метод 1: Парсинг GLOBAL_PROJECTS.md
        if self.global_projects_file.exists():
            try:
                content = self.global_projects_file.read_text(encoding='utf-8')
                # Ищем строки с "**Память:** `~/.claude/projects/XXX/memory/`"
                pattern = (r'\*\*Память:\*\*\s+'
                          r'`~/.claude/projects/([^/]+)/memory/`')
                matches = re.findall(pattern, content)
                for match in matches:
                    projects.add(match)
                    print(f"[AUTO] Found project in GLOBAL_PROJECTS.md: {match}")

                # Если нашли проекты в GLOBAL_PROJECTS.md - используем только их
                if projects:
                    print(f"[AUTO] Using {len(projects)} projects from GLOBAL_PROJECTS.md")
                    return sorted(list(projects))
            except Exception as e:
                print(f"[WARN] Failed to parse GLOBAL_PROJECTS.md: {e}")

        # Метод 2: Fallback - автоопределение по memory/ с файлами
        # Используется ТОЛЬКО если GLOBAL_PROJECTS.md не найден или пуст
        print("[AUTO] GLOBAL_PROJECTS.md not found or empty, using fallback detection")

        if self.projects_base.exists():
            for project_dir in self.projects_base.iterdir():
                if not project_dir.is_dir():
                    continue

                # Пропускаем очевидно системные директории
                name_lower = project_dir.name.lower()
                if any(x in name_lower for x in ['windows', 'system32', 'users']):
                    print(f"[AUTO] Skipping system directory: {project_dir.name}")
                    continue

                # Пропускаем короткие имена (C--BAT) - скорее всего временные CWD
                # Настоящие проекты обычно длиннее: C--BAT-msfs-autoland
                if len(project_dir.name) < 10:
                    print(f"[AUTO] Skipping short name (likely temp CWD): {project_dir.name}")
                    continue

                # Проверяем наличие memory/ с .md файлами
                memory_path = project_dir / "memory"
                if memory_path.exists():
                    md_files = list(memory_path.glob("*.md"))
                    # Требуем минимум 3 .md файла (handoff, decisions, MEMORY)
                    if len(md_files) >= 3:
                        projects.add(project_dir.name)
                        msg = (f"[AUTO] Found project by memory/ presence: "
                               f"{project_dir.name} ({len(md_files)} files)")
                        print(msg)
                    else:
                        print(f"[AUTO] Skipping {project_dir.name}: only {len(md_files)} .md files")

        if not projects:
            print("[WARN] No projects discovered, using empty whitelist")

        return sorted(list(projects))

    def get_or_create_collection(self, name: str, description: str):
        """Получить или создать коллекцию"""
        return self.client.get_or_create_collection(
            name=name,
            metadata={"description": description}
        )

    def index_global_memory(self) -> bool:
        """Индексирует глобальную память с batch обработкой"""
        logging.info("Indexing global memory: %s", self.global_memory)

        if not self.global_memory.exists():
            print(f"[ERROR] Global memory not found: {self.global_memory}")
            return False

        # Проверка прав доступа к директории
        if not os.access(self.global_memory, os.R_OK):
            print(f"[ERROR] No read access to: {self.global_memory}")
            return False

        collection = self.get_or_create_collection(
            self.config['collection_names']['global'],
            "Global memory - knowledge applicable to all projects"
        )

        # Собираем все файлы
        md_files = [f for f in self.global_memory.rglob("*.md")
                    if not f.name.startswith('.')]

        # Batch индексация с параллелизмом
        indexed_count = self._index_files_batch(md_files, collection, "global")

        print(f"[OK] Indexed {indexed_count} files from global memory")
        return True

    def index_project(self, project_path: Path) -> bool:
        """Индексирует память конкретного проекта с batch обработкой"""
        memory_path = project_path / "memory"

        if not memory_path.exists():
            print(f"[ERROR] Project memory not found: {memory_path}")
            return False

        # Проверка прав доступа
        if not os.access(memory_path, os.R_OK):
            print(f"[ERROR] No read access to: {memory_path}")
            return False

        project_name = self.normalize_project_name(project_path.name)
        prefix = self.config['collection_names']['project_prefix']
        collection = self.get_or_create_collection(
            f"{prefix}{project_name}",
            f"Project memory: {project_name}"
        )

        logging.info("Indexing project: %s", project_name)

        # Собираем все файлы
        md_files = [f for f in memory_path.rglob("*.md")
                    if not f.name.startswith('.')]

        # Batch индексация
        indexed_count = self._index_files_batch(md_files, collection, project_name)

        print(f"[OK] Indexed {indexed_count} files from {project_name}")
        return True

    def index_all_projects(self) -> bool:
        """Индексирует все проекты"""
        if not self.projects_base.exists():
            print(f"[ERROR] Projects directory not found: {self.projects_base}")
            return False

        # Индексируем глобальную память
        self.index_global_memory()

        # Индексируем только проекты из whitelist
        for project_dir in self.projects_base.iterdir():
            if not project_dir.is_dir():
                continue

            # Проверка whitelist
            if project_dir.name not in self.project_whitelist:
                print(f"[SKIP] {project_dir.name} (not in whitelist)")
                continue

            if (project_dir / "memory").exists():
                self.index_project(project_dir)
            else:
                print(f"[WARN] {project_dir.name} in whitelist but no memory/ found")

        return True

    def search_global(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Поиск только в глобальной памяти"""
        try:
            collection = self.client.get_collection(self.config['collection_names']['global'])
            return self._search_in_collection(collection, query, n_results, "global")
        except Exception as e:
            print(f"[ERROR] Global collection not found: {e}")
            return []

    def search_project(self, project_name: str, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Поиск в конкретном проекте"""
        prefix = self.config['collection_names']['project_prefix']
        collection_name = f"{prefix}{self.normalize_project_name(project_name)}"
        try:
            collection = self.client.get_collection(collection_name)
            return self._search_in_collection(collection, query, n_results, project_name)
        except Exception as e:
            print(f"[ERROR] Project collection not found: {e}")
            return []

    def search_all(self, query: str, n_results: int = 10) -> List[Dict[str, Any]]:
        """Cross-collection search (global + every project).

        Encodes the query once and reuses the embedding across all
        collections instead of paying the SentenceTransformer cost
        per-collection. With N projects this turns N encodings into 1.
        """
        query_embedding = self.model.encode([query]).tolist()

        all_results: List[Dict[str, Any]] = []

        # Поиск в глобальной памяти (passing the pre-computed embedding).
        global_name = self.config['collection_names']['global']
        try:
            global_collection = self.client.get_collection(global_name)
            all_results.extend(
                self._search_in_collection(
                    global_collection, query, n_results, "global",
                    query_embedding=query_embedding,
                )
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.warning("Global collection not available: %s", exc)

        # Поиск во всех проектных коллекциях. Defensive: skip the global
        # collection even if it happens to share the project prefix.
        prefix = self.config['collection_names']['project_prefix']
        collections = self.client.list_collections()
        for collection_info in collections:
            if not collection_info.name.startswith(prefix):
                continue
            if collection_info.name == global_name:
                continue
            collection = self.client.get_collection(collection_info.name)
            project_name = collection_info.name[len(prefix):]
            all_results.extend(
                self._search_in_collection(
                    collection, query, n_results // 2, project_name,
                    query_embedding=query_embedding,
                )
            )

        # Сортируем по релевантности (distance)
        all_results.sort(key=lambda x: x.get('distance', 999))

        return all_results[:n_results]

    def stats(self) -> Dict[str, Any]:
        """Статистика всех коллекций"""
        collections = self.client.list_collections()

        stats: Dict[str, Any] = {
            'db_path': str(self.db_path),
            'total_collections': len(collections),
            'collections': {}
        }

        for collection_info in collections:
            collection = self.client.get_collection(collection_info.name)
            desc = ''
            if collection_info.metadata:
                desc = collection_info.metadata.get('description', '')
            collection_stats: Dict[str, Any] = {
                'chunks': collection.count(),
                'description': desc
            }
            stats['collections'][collection_info.name] = collection_stats

        return stats

    def cleanup_collections(self, dry_run: bool = True) -> Dict[str, Any]:
        """Очистка мусорных коллекций

        Args:
            dry_run: Если True, только показывает что будет удалено

        Returns:
            Словарь с результатами очистки
        """
        collections = self.client.list_collections()

        # Валидные коллекции
        prefix = self.config['collection_names']['project_prefix']
        valid_collections = {self.config['collection_names']['global']}
        for project in self.project_whitelist:
            valid_collections.add(f"{prefix}{self.normalize_project_name(project)}")

        to_delete = []
        to_keep = []

        for collection_info in collections:
            if collection_info.name in valid_collections:
                collection = self.client.get_collection(collection_info.name)
                to_keep.append({
                    'name': collection_info.name,
                    'chunks': collection.count()
                })
            else:
                collection = self.client.get_collection(collection_info.name)
                to_delete.append({
                    'name': collection_info.name,
                    'chunks': collection.count(),
                    'reason': 'not in whitelist'
                })

        result = {
            'dry_run': dry_run,
            'to_keep': to_keep,
            'to_delete': to_delete,
            'deleted': []
        }

        if not dry_run:
            deleted_list: List[str] = []
            for item in to_delete:
                try:
                    self.client.delete_collection(item['name'])
                    deleted_list.append(item['name'])
                    print(f"[DELETED] {item['name']} ({item['chunks']} chunks)")
                except Exception as e:
                    print(f"[ERROR] Failed to delete {item['name']}: {e}")
            result['deleted'] = deleted_list
        else:
            print("[DRY RUN] Collections that would be deleted:")
            for item in to_delete:
                print(f"  - {item['name']} ({item['chunks']} chunks) - {item['reason']}")

        return result

    def _index_files_batch(self, files: List[Path], collection, source: str) -> int:
        """Batch индексация файлов с параллелизмом"""
        batch_size = self.config['batch_size']
        max_workers = self.config['max_workers']
        indexed_count = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self._prepare_file_data, f, source): f
                for f in files
            }

            batch_data = []
            for future in as_completed(futures):
                try:
                    data = future.result()
                    if data:
                        batch_data.append(data)

                        # Когда накопили batch_size файлов - добавляем в БД
                        if len(batch_data) >= batch_size:
                            self._add_batch_to_collection(batch_data, collection)
                            indexed_count += len(batch_data)
                            batch_data = []
                except Exception as e:
                    file_path = futures[future]
                    print(f"[ERROR] Failed to prepare {file_path.name}: {e}")

            # Добавляем остаток
            if batch_data:
                self._add_batch_to_collection(batch_data, collection)
                indexed_count += len(batch_data)

        return indexed_count

    def _prepare_file_data(self, file_path: Path, source: str) -> Dict[str, Any]:
        """Read a markdown file, split it into chunks, and prepare a Chroma payload.

        Returns ``{}`` when the file is unreadable, empty, or contains
        only a YAML frontmatter block (no body) — those cases are skipped
        with a warning so they don't silently disappear from the index.
        """
        # Проверка прав доступа
        if not os.access(file_path, os.R_OK):
            logging.warning("No read access to %s", file_path)
            return {}

        content = file_path.read_text(encoding='utf-8')

        # Парсинг метаданных
        metadata = self._parse_frontmatter(content)

        # Разбиваем на чанки
        chunks = self._split_into_chunks(content)

        if not chunks:
            logging.warning(
                "Skipping %s: no indexable content (frontmatter-only or empty)",
                file_path,
            )
            return {}

        # Генерируем эмбеддинги
        embeddings = self.model.encode(chunks).tolist()

        # Формируем данные. Имя файла нормализуется в ASCII-safe форму,
        # чтобы ChromaDB не споткнулся на не-ASCII stem (например, "тест.md").
        stem_safe = self._normalize_id_part(file_path.stem)
        ids = [f"{source}_{stem_safe}_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "file": file_path.name,
                "source": source,
                "chunk_id": i,
                "indexed_at": datetime.now().isoformat(),
                **metadata
            }
            for i in range(len(chunks))
        ]

        return {
            'file_path': file_path,
            'source': source,
            'ids': ids,
            'embeddings': embeddings,
            'documents': chunks,
            'metadatas': metadatas
        }

    def _add_batch_to_collection(self, batch_data: List[Dict[str, Any]], collection):
        """Add a batch of file payloads to a Chroma collection.

        Coalesces stale-row deletion and the new-row ``add`` into one
        ``get`` + at most one ``delete`` + one ``add`` call per batch
        instead of three calls per file. With the previous per-file loop
        a 50-file reindex was 150 round-trips to Chroma; now it's 3,
        which is a meaningful win for SQLite-backed Chroma installs.

        On bulk-add failure we fall back to per-file inserts so a single
        bad payload doesn't lose the whole batch.
        """
        if not batch_data:
            return

        # 1. Bulk delete of stale rows for every (file, source) pair in this batch.
        or_clauses = [
            {
                "$and": [
                    {"file": {"$eq": data['file_path'].name}},
                    {"source": {"$eq": data['source']}},
                ]
            }
            for data in batch_data
        ]
        where = or_clauses[0] if len(or_clauses) == 1 else {"$or": or_clauses}

        try:
            existing = collection.get(where=where)
            stale_ids = existing.get("ids", [])
            if stale_ids:
                collection.delete(ids=stale_ids)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.warning("Bulk stale-row cleanup failed, continuing: %s", exc)

        # 2. Bulk add of all new rows.
        all_ids: List[str] = []
        all_embeddings: List[Any] = []
        all_documents: List[str] = []
        all_metadatas: List[Dict[str, Any]] = []
        for data in batch_data:
            all_ids.extend(data['ids'])
            all_embeddings.extend(data['embeddings'])
            all_documents.extend(data['documents'])
            all_metadatas.extend(data['metadatas'])

        if not all_ids:
            return

        try:
            collection.add(
                ids=all_ids,
                embeddings=all_embeddings,
                documents=all_documents,
                metadatas=all_metadatas,
            )
        except Exception as bulk_exc:  # pylint: disable=broad-exception-caught
            logging.warning(
                "Bulk add failed (%s); falling back to per-file inserts", bulk_exc
            )
            for data in batch_data:
                try:
                    collection.add(
                        ids=data['ids'],
                        embeddings=data['embeddings'],
                        documents=data['documents'],
                        metadatas=data['metadatas'],
                    )
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    logging.warning(
                        "Failed to add %s to collection: %s",
                        data['file_path'].name, exc,
                    )

    def _search_in_collection(
        self,
        collection,
        query: str,
        n_results: int,
        source: str,
        *,
        query_embedding: Optional[Sequence[Sequence[float]]] = None,
    ) -> List[Dict[str, Any]]:
        """Run a Chroma query against one collection and normalise the result.

        ``query_embedding`` may be passed in by the caller — that lets
        ``search_all`` encode the query once and reuse the vector across
        every project collection instead of re-encoding for each one.

        We also clamp ``range`` to the shortest of ``ids`` / ``documents``
        / ``metadatas`` so a malformed Chroma response (e.g. a partial
        truncation) cannot cause an ``IndexError`` halfway through
        formatting.
        """
        if query_embedding is None:
            query_embedding = self.model.encode([query]).tolist()

        results = collection.query(
            query_embeddings=query_embedding,
            n_results=n_results,
        )

        formatted: List[Dict[str, Any]] = []
        ids_outer = results.get('ids') or []
        if not ids_outer or not ids_outer[0]:
            return formatted

        ids = ids_outer[0]
        docs = (results.get('documents') or [[]])[0]
        metas = (results.get('metadatas') or [[]])[0]
        distances_outer = results.get('distances') or []
        distances = distances_outer[0] if distances_outer else []

        # Defensive: trim to the shortest parallel array so we never
        # index past the end of one of them if Chroma returns mismatched
        # lengths (it shouldn't, but the cost of being safe is one min()).
        n = min(len(ids), len(docs), len(metas))
        for i in range(n):
            distance = distances[i] if i < len(distances) else None
            formatted.append({
                'id': ids[i],
                'text': docs[i],
                'metadata': metas[i],
                'distance': distance,
                'source': source,
            })

        return formatted

    @lru_cache(maxsize=128)
    def _parse_frontmatter(self, content: str) -> Dict[str, str]:
        """Извлекает метаданные из frontmatter (с кешированием)"""
        metadata = {}
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                frontmatter = parts[1].strip()
                for line in frontmatter.split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        metadata[key.strip()] = value.strip()
        return metadata

    def _split_into_chunks(self, content: str) -> List[str]:
        """Разбивает контент на чанки"""
        max_chunk_size = self.config['max_chunk_size']

        if content.startswith('---'):
            parts = content.split('---', 2)
            content = parts[2] if len(parts) >= 3 else content

        sections = []
        current_section: List[str] = []

        for line in content.split('\n'):
            if line.startswith('##') and current_section:
                sections.append('\n'.join(current_section))
                current_section = [line]
            else:
                current_section.append(line)

        if current_section:
            sections.append('\n'.join(current_section))

        chunks = []
        for section in sections:
            if len(section) <= max_chunk_size:
                chunks.append(section.strip())
            else:
                paragraphs = section.split('\n\n')
                for para in paragraphs:
                    if para.strip():
                        chunks.append(para.strip())

        return [c for c in chunks if c]


def format_distance(distance) -> str:
    """
    Форматирование distance для отображения.

    Args:
        distance: Значение distance (float, int или None)

    Returns:
        Отформатированная строка ("0.123" или "N/A")
    """
    return f"{distance:.3f}" if isinstance(distance, (int, float)) else "N/A"


@dataclass
class CommandConfig:
    """Configuration for command execution"""
    command: str
    args: List[str]
    memory: 'GlobalSemanticMemory'


def parse_command_line() -> CommandConfig:
    """Parse command line arguments (extracted per Alisa's recommendation)"""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    args = sys.argv[2:] if len(sys.argv) > 2 else []
    memory = GlobalSemanticMemory()

    return CommandConfig(command=command, args=args, memory=memory)


def execute_index_global(config: CommandConfig) -> None:
    """Execute index-global command"""
    config.memory.index_global_memory()


def execute_index_project(config: CommandConfig) -> None:
    """Execute index-project command"""
    if not config.args:
        print("Usage: l4_semantic_global.py index-project <project-path>")
        sys.exit(1)
    project_path = Path(config.args[0])
    config.memory.index_project(project_path)


def execute_index_all(config: CommandConfig) -> None:
    """Execute index-all command"""
    config.memory.index_all_projects()


def execute_search_global(config: CommandConfig) -> None:
    """Execute search-global command"""
    if not config.args:
        print("Usage: l4_semantic_global.py search-global <query>")
        sys.exit(1)

    query = ' '.join(config.args)
    results = config.memory.search_global(query)

    print(f"\n[SEARCH GLOBAL] '{query}'\n")
    for i, result in enumerate(results, 1):
        distance = result.get('distance')
        distance_str = format_distance(distance)
        print(f"[{i}] {result['metadata']['file']} (distance: {distance_str})")
        print(f"    {result['text'][:200]}...")
        print()


def execute_search_project(config: CommandConfig) -> None:
    """Execute search-project command"""
    if len(config.args) < 2:
        print("Usage: l4_semantic_global.py search-project <project-name> <query>")
        sys.exit(1)

    project_name = config.args[0]
    query = ' '.join(config.args[1:])
    results = config.memory.search_project(project_name, query)

    print(f"\n[SEARCH PROJECT: {project_name}] '{query}'\n")
    for i, result in enumerate(results, 1):
        distance = result.get('distance')
        distance_str = format_distance(distance)
        print(f"[{i}] {result['metadata']['file']} (distance: {distance_str})")
        print(f"    {result['text'][:200]}...")
        print()


def execute_search_all(config: CommandConfig) -> None:
    """Execute search-all command.

    Supports a ``--json`` flag for machine-readable output, used by
    :func:`scripts.l4_fts5_search.cmd_hybrid` when assembling the
    inputs for Reciprocal Rank Fusion. Without the flag the output
    is the same human-readable format as before.
    """
    json_mode = '--json' in config.args
    text_args = [a for a in config.args if a != '--json']
    if not text_args:
        print("Usage: l4_semantic_global.py search-all <query> [--json]")
        sys.exit(1)

    query = ' '.join(text_args)
    results = config.memory.search_all(query)

    if json_mode:
        # Slim JSON envelope so the consumer doesn't have to know the
        # full ChromaDB result schema. ``key`` is the join field used
        # by the RRF merger; everything else is preserved for
        # explainability.
        payload = {
            'query': query,
            'results': [
                {
                    'key': f"[{r['source']}] {r.get('metadata', {}).get('file', '')}",
                    'source_scope': r['source'],
                    'file': r.get('metadata', {}).get('file', ''),
                    'distance': r.get('distance'),
                    'text': r.get('text', ''),
                }
                for r in results
            ],
        }
        print(json.dumps(payload, ensure_ascii=False))
        return

    print(f"\n[SEARCH ALL] '{query}'\n")
    for i, result in enumerate(results, 1):
        source = result['source']
        distance = result.get('distance')
        distance_str = format_distance(distance)
        print(f"[{i}] [{source}] {result['metadata']['file']} "
              f"(distance: {distance_str})")
        print(f"    {result['text'][:200]}...")
        print()


def execute_stats(config: CommandConfig) -> None:
    """Execute stats command"""
    stats = config.memory.stats()
    print("\n[STATS] L4 SEMANTIC Global Statistics:")
    print(f"   DB path: {stats['db_path']}")
    print(f"   Total collections: {stats['total_collections']}")
    print("\n   Collections:")
    for name, info in stats['collections'].items():
        print(f"      {name}: {info['chunks']} chunks")
        print(f"         {info['description']}")


def execute_cleanup(config: CommandConfig) -> None:
    """Execute cleanup command"""
    dry_run = '--dry-run' in sys.argv or '-n' in sys.argv
    result = config.memory.cleanup_collections(dry_run=dry_run)

    print("\n[CLEANUP] L4 SEMANTIC Collections")
    print(f"   Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print(f"\n   Keep ({len(result['to_keep'])}):")
    for item in result['to_keep']:
        print(f"      ✓ {item['name']} ({item['chunks']} chunks)")

    print(f"\n   Delete ({len(result['to_delete'])}):")
    for item in result['to_delete']:
        status = '✗' if dry_run else '🗑'
        reason = item['reason']
        print(f"      {status} {item['name']} ({item['chunks']} chunks) - {reason}")

    if dry_run:
        print("\n   Run without --dry-run to actually delete")
    else:
        print(f"\n   Deleted: {len(result.get('deleted', []))} collections")


def execute_command(config: CommandConfig) -> None:
    """Execute command based on config (extracted per Alisa's recommendation)"""
    commands = {
        'index-global': execute_index_global,
        'index-project': execute_index_project,
        'index-all': execute_index_all,
        'search-global': execute_search_global,
        'search-project': execute_search_project,
        'search-all': execute_search_all,
        'stats': execute_stats,
        'cleanup': execute_cleanup
    }

    handler = commands.get(config.command)
    if handler:
        handler(config)
    else:
        print(f"Unknown command: {config.command}")
        print(__doc__)
        sys.exit(1)


def main():
    """Main entry point (refactored per Alisa's recommendations)"""
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='[%(levelname)s] %(message)s'
    )

    try:
        config = parse_command_line()
        execute_command(config)
    except Exception as e:
        logging.error("Critical error: %s", e)
        sys.exit(1)


if __name__ == '__main__':
    main()
