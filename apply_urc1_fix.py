from pathlib import Path

p = Path('scripts/l4_semantic_global.py')
content = p.read_text('utf-8')

# обавить импорт, если отсутствует
import_line = 'from ranking import rrf_merge, rank_results, RankedResult'
if import_line not in content:
    content = content.replace(
        '\n\nclass GlobalSemanticMemory:',
        f'\n{import_line}\n\nclass GlobalSemanticMemory:',
        1
    )

# аменить метод search_all — от def до следующего def
old = '''    def search_all(self, query: str, n_results: int = 10) -> List[Dict[str, Any]]:
        """љСЂѕсс-їСЂѕµєС‚ЅС‹ їѕёСЃє (і»ѕ±°»СЊЅ°СЏ + ІСЃµ їСЂѕµєты)"""
        all_results = []
        query_embedding = self._encode_query(query)

        # џѕёСЃє І і»ѕ±°»СЊЅѕ ї°јятё
        collection = self.client.get_collection(
            self.config['collection_names']['global'])
        global_results = self._search_in_collection(
            collection, query, n_results, "global",
            query_embedding=query_embedding)
        all_results.extend(global_results)

        # џѕёСЃє Іѕ ІСЃµС… їСЂѕµєС‚°С…
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

new = '''    def search_all(self, query: str, n_results: int = 10) -> List[Dict[str, Any]]:
        """росс-проектный поиск (глобальная + все проекты) с RRF-ранжированием."""
        all_results = []
        query_embedding = self._encode_query(query)

        # оиск в глобальной памяти
        collection = self.client.get_collection(
            self.config['collection_names']['global'])
        global_results = self._search_in_collection(
            collection, query, n_results, "global",
            query_embedding=query_embedding)
        all_results.extend(global_results)

        # оиск во всех проектах
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

        # сли результаты только из одного источника — применяем rank_results
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

        # онвертируем обратно в словари для обратной совместимости
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

if old in content:
    content = content.replace(old, new)
    print('[OK] search_all replaced')
else:
    print('[WARN] Old search_all not found — may already be replaced')

p.write_text(content, 'utf-8')
print('[OK] l4_semantic_global.py updated')
