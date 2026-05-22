from pathlib import Path

p = Path('scripts/l4_semantic_global.py')
content = p.read_text('utf-8')

# 1. Добавить импорт, если его ещё нет
import_line = 'from ranking import rrf_merge, rank_results, RankedResult'
if import_line not in content:
    # Вставляем после последнего импорта, перед class GlobalSemanticMemory
    content = content.replace(
        '\n\nclass GlobalSemanticMemory:',
        f'\n{import_line}\n\nclass GlobalSemanticMemory:',
        1
    )

# 2. Заменить метод search_all
old_search_all = '''    def search_all(self, query: str, n_results: int = 10) -> List[Dict[str, Any]]:
        """Кросс-проектный поиск (глобальная + все проекты)"""
        all_results = []
        query_embedding = self._encode_query(query)

        # Поиск в глобальной памяти
        collection = self.client.get_collection(
            self.config['collection_names']['global'])
        global_results = self._search_in_collection(
            collection, query, n_results, "global",
            query_embedding=query_embedding)
        all_results.extend(global_results)

        # Поиск во всех проектах
        prefix = self.config['collection_names']['project_prefix']
        global_name = self.config['collection_names']['global']
        for collection_info in self.client.list_collections():
            if (collection_info.name.startswith(prefix) and
                    collection_info.name != global_name):
                collection = self.client.get_collection(collection_info.name)
                project_name = collection_info.name[len(prefix):]
                results = self._search_in_collection(
                    collection, query, n_results // 2, project_name,
                    query_embedding=query_embedding)
                all_results.extend(results)

        all_results.sort(key=lambda x: x.get('distance', 999))

        return all_results[:n_results]'''

new_search_all = '''    def search_all(self, query: str, n_results: int = 10) -> List[Dict[str, Any]]:
        """Кросс-проектный поиск (глобальная + все проекты) с RRF-ранжированием."""
        all_results = []
        query_embedding = self._encode_query(query)

        # Поиск в глобальной памяти
        collection = self.client.get_collection(
            self.config['collection_names']['global'])
        global_results = self._search_in_collection(
            collection, query, n_results, "global",
            query_embedding=query_embedding)
        all_results.extend(global_results)

        # Поиск во всех проектах
        prefix = self.config['collection_names']['project_prefix']
        global_name = self.config['collection_names']['global']
        for collection_info in self.client.list_collections():
            if (collection_info.name.startswith(prefix) and
                    collection_info.name != global_name):
                collection = self.client.get_collection(collection_info.name)
                project_name = collection_info.name[len(prefix):]
                results = self._search_in_collection(
                    collection, query, n_results // 2, project_name,
                    query_embedding=query_embedding)
                all_results.extend(results)

        # Если результаты только из одного источника — применяем rank_results
        # с rrf_score = 1/(k+rank) для сохранения контракта сортировки
        ranked = []
        for i, r in enumerate(all_results):
            ranked.append(RankedResult(
                id=r['id'],
                text=r['text'],
                metadata=r['metadata'],
                source=r['source'],
                rrf_score=1.0 / (60 + i + 1),  # RRF с одним источником
                distance=r.get('distance')
            ))

        ranked = rank_results(ranked)

        # Конвертируем обратно в словари для обратной совместимости
        return [
            {
                'id': r.id,
                'text': r.text,
                'metadata': r.metadata,
                'source': r.source,
                'rrf_score': r.rrf_score,
                'distance': r.distance
            }
            for r in ranked[:n_results]
        ]'''

if old_search_all in content:
    content = content.replace(old_search_all, new_search_all)
    print('[OK] search_all replaced')
else:
    print('[WARN] Old search_all not found – may already be updated')

p.write_text(content, 'utf-8')
print('[OK] l4_semantic_global.py updated')