#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
"""

import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

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

    def __init__(self):
        """Инициализация с автоопределением путей"""
        self.home = Path.home()
        self.global_memory = self.home / ".claude" / "memory"
        self.projects_base = self.home / ".claude" / "projects"
        self.global_projects_file = self.home / ".claude" / "GLOBAL_PROJECTS.md"

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
        model_name = os.getenv('L4_MODEL', 'paraphrase-multilingual-MiniLM-L12-v2')
        print(f"[INFO] Loading embedding model: {model_name}")
        self.model = SentenceTransformer(model_name)

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
        """Индексирует глобальную память"""
        print(f"[INFO] Indexing global memory: {self.global_memory}")

        if not self.global_memory.exists():
            print(f"[ERROR] Global memory not found: {self.global_memory}")
            return False

        collection = self.get_or_create_collection(
            "memory_global",
            "Global memory - knowledge applicable to all projects"
        )

        # Индексируем все .md файлы
        indexed_count = 0
        for md_file in self.global_memory.rglob("*.md"):
            if md_file.name.startswith('.'):
                continue

            try:
                self._index_file(md_file, collection, "global")
                indexed_count += 1
            except Exception as e:
                print(f"[ERROR] Failed to index {md_file.name}: {e}")

        print(f"[OK] Indexed {indexed_count} files from global memory")
        return True

    def index_project(self, project_path: Path) -> bool:
        """Индексирует память конкретного проекта"""
        memory_path = project_path / "memory"

        if not memory_path.exists():
            print(f"[ERROR] Project memory not found: {memory_path}")
            return False

        project_name = project_path.name.replace("-", "_")
        collection = self.get_or_create_collection(
            f"memory_{project_name}",
            f"Project memory: {project_name}"
        )

        print(f"[INFO] Indexing project: {project_name}")

        indexed_count = 0
        for md_file in memory_path.rglob("*.md"):
            if md_file.name.startswith('.'):
                continue

            try:
                self._index_file(md_file, collection, project_name)
                indexed_count += 1
            except Exception as e:
                print(f"[ERROR] Failed to index {md_file.name}: {e}")

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
            collection = self.client.get_collection("memory_global")
            return self._search_in_collection(collection, query, n_results, "global")
        except Exception as e:
            print(f"[ERROR] Global collection not found: {e}")
            return []

    def search_project(self, project_name: str, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Поиск в конкретном проекте"""
        collection_name = f"memory_{project_name.replace('-', '_')}"
        try:
            collection = self.client.get_collection(collection_name)
            return self._search_in_collection(collection, query, n_results, project_name)
        except Exception as e:
            print(f"[ERROR] Project collection not found: {e}")
            return []

    def search_all(self, query: str, n_results: int = 10) -> List[Dict[str, Any]]:
        """Кросс-проектный поиск (глобальная + все проекты)"""
        all_results = []

        # Поиск в глобальной памяти
        global_results = self.search_global(query, n_results)
        all_results.extend(global_results)

        # Поиск во всех проектах
        collections = self.client.list_collections()
        for collection_info in collections:
            if collection_info.name.startswith("memory_") and collection_info.name != "memory_global":
                collection = self.client.get_collection(collection_info.name)
                project_name = collection_info.name.replace("memory_", "")
                results = self._search_in_collection(collection, query, n_results // 2, project_name)
                all_results.extend(results)

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
        valid_collections = {"memory_global"}
        for project in self.project_whitelist:
            valid_collections.add(f"memory_{project.replace('-', '_')}")

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

    def _index_file(self, file_path: Path, collection, source: str):
        """Индексирует файл в коллекцию"""
        content = file_path.read_text(encoding='utf-8')

        # Парсинг метаданных
        metadata = self._parse_frontmatter(content)

        # Разбиваем на чанки
        chunks = self._split_into_chunks(content)

        if not chunks:
            return

        # Генерируем эмбеддинги
        embeddings = self.model.encode(chunks).tolist()

        # Добавляем в БД
        ids = [f"{source}_{file_path.stem}_{i}" for i in range(len(chunks))]
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

        # Удаляем старые записи для этого файла по метаданным
        try:
            collection.delete(where={"file": file_path.name, "source": source})
        except Exception as e:
            logging.warning("Could not delete existing embeddings for %s: %s", file_path.name, e)

        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas
        )

    def _search_in_collection(
        self, collection, query: str, n_results: int, source: str
    ) -> List[Dict[str, Any]]:
        """Поиск в конкретной коллекции"""
        query_embedding = self.model.encode([query]).tolist()

        results = collection.query(
            query_embeddings=query_embedding,
            n_results=n_results
        )

        formatted = []
        for i in range(len(results['ids'][0])):
            formatted.append({
                'id': results['ids'][0][i],
                'text': results['documents'][0][i],
                'metadata': results['metadatas'][0][i],
                'distance': results['distances'][0][i] if 'distances' in results else None,
                'source': source
            })

        return formatted

    def _parse_frontmatter(self, content: str) -> Dict[str, str]:
        """Извлекает метаданные из frontmatter"""
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

    def _split_into_chunks(self, content: str, max_chunk_size: int = 500) -> List[str]:
        """Разбивает контент на чанки"""
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


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    memory = GlobalSemanticMemory()

    if command == 'index-global':
        memory.index_global_memory()

    elif command == 'index-project':
        if len(sys.argv) < 3:
            print("Usage: l4_semantic_global.py index-project <project-path>")
            sys.exit(1)
        project_path = Path(sys.argv[2])
        memory.index_project(project_path)

    elif command == 'index-all':
        memory.index_all_projects()

    elif command == 'search-global':
        if len(sys.argv) < 3:
            print("Usage: l4_semantic_global.py search-global <query>")
            sys.exit(1)
        query = ' '.join(sys.argv[2:])
        results = memory.search_global(query)

        print(f"\n[SEARCH GLOBAL] '{query}'\n")
        for i, result in enumerate(results, 1):
            distance = result.get('distance')
            distance_str = f"{distance:.3f}" if isinstance(distance, (int, float)) else "N/A"
            print(f"[{i}] {result['metadata']['file']} (distance: {distance_str})")
            print(f"    {result['text'][:200]}...")
            print()

    elif command == 'search-project':
        if len(sys.argv) < 4:
            print("Usage: l4_semantic_global.py search-project <project-name> <query>")
            sys.exit(1)
        project_name = sys.argv[2]
        query = ' '.join(sys.argv[3:])
        results = memory.search_project(project_name, query)

        print(f"\n[SEARCH PROJECT: {project_name}] '{query}'\n")
        for i, result in enumerate(results, 1):
            distance = result.get('distance')
            distance_str = f"{distance:.3f}" if isinstance(distance, (int, float)) else "N/A"
            print(f"[{i}] {result['metadata']['file']} (distance: {distance_str})")
            print(f"    {result['text'][:200]}...")
            print()

    elif command == 'search-all':
        if len(sys.argv) < 3:
            print("Usage: l4_semantic_global.py search-all <query>")
            sys.exit(1)
        query = ' '.join(sys.argv[2:])
        results = memory.search_all(query)

        print(f"\n[SEARCH ALL] '{query}'\n")
        for i, result in enumerate(results, 1):
            source = result['source']
            distance = result.get('distance')
            distance_str = f"{distance:.3f}" if isinstance(distance, (int, float)) else "N/A"
            print(f"[{i}] [{source}] {result['metadata']['file']} "
                  f"(distance: {distance_str})")
            print(f"    {result['text'][:200]}...")
            print()

    elif command == 'stats':
        stats = memory.stats()
        print("\n[STATS] L4 SEMANTIC Global Statistics:")
        print(f"   DB path: {stats['db_path']}")
        print(f"   Total collections: {stats['total_collections']}")
        print("\n   Collections:")
        for name, info in stats['collections'].items():
            print(f"      {name}: {info['chunks']} chunks")
            print(f"         {info['description']}")

    elif command == 'cleanup':
        dry_run = '--dry-run' in sys.argv or '-n' in sys.argv
        result = memory.cleanup_collections(dry_run=dry_run)

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
            print(f"\n   Deleted: {len(result['deleted'])} collections")

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()
