# Cross-Encoder Reranking

**Version:** 1.0  
**Added:** 2026-05-07  
**Status:** Production Ready

---

## Overview

Cross-encoder reranking is the final stage of the hybrid search pipeline that significantly improves result relevance by re-scoring the top candidates using a neural cross-encoder model.

Unlike bi-encoders (used in semantic search) that encode query and documents independently, cross-encoders process query-document pairs jointly, capturing fine-grained semantic interactions that lead to more accurate relevance scores.

---

## Architecture

### Pipeline Position

```
┌─────────────────────────────────────────────────────────────┐
│                    Hybrid Search Pipeline                    │
└─────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │   FTS5 (BM25)     │  Keyword matching
                    │   Semantic Search │  Meaning-based
                    │   BM25 Ranking    │  Statistical
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │  RRF Fusion       │  Merge signals
                    │  (Top-100)        │
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │ Cross-Encoder     │  ← THIS STAGE
                    │ Reranking         │
                    │ (Top-20)          │
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │  Final Results    │
                    └───────────────────┘
```

### Model Details

**Model:** `cross-encoder/ms-marco-MiniLM-L-6-v2`

**Specifications:**
- **Architecture:** BERT-based cross-encoder
- **Parameters:** ~23M
- **Training:** MS MARCO passage ranking dataset
- **Input:** Query + document pairs (max 512 tokens)
- **Output:** Relevance score (float, unbounded)

**Performance:**
- **Inference time:** ~15-20ms per pair
- **Batch processing:** 20 pairs in ~300ms
- **Memory:** ~100MB model size

---

## Usage

### Command Line

#### Hybrid Search (with reranking by default)

```bash
python scripts/l4_fts5_search.py hybrid "memory system"
```

**Output:**
```
[RERANKING] Applying cross-encoder to top-15 results...
[RERANKING] Completed in 0.313s, 10/10 positions changed in top-10

Merged 15 unique result(s)
----------------------------------------------------------------------
[1] [project] file.md  score=0.0328  normalized=1.000  rerank=6.5924  sources=[fts, semantic]
```

#### Disable Reranking

```bash
python scripts/l4_fts5_search.py hybrid --no-rerank "memory system"
```

**Output:**
```
Merged 15 unique result(s)
----------------------------------------------------------------------
[1] [project] file.md  score=0.0328  normalized=1.000  sources=[fts, semantic]
```

### Programmatic API

```python
from scripts.l4_rerank import rerank
from scripts.ranking import RankedResult

# After RRF merge
candidates = [
    RankedResult(
        key="doc1.md",
        score=0.5,
        sources={"fts": [{"snippet": "memory system architecture"}]}
    ),
    RankedResult(
        key="doc2.md",
        score=0.3,
        sources={"semantic": [{"snippet": "unrelated content"}]}
    )
]

# Apply reranking
reranked = rerank("memory system", candidates)

# Access rerank scores
for result in reranked:
    print(f"{result.key}: rerank_score={result.rerank_score:.4f}")
```

**Output:**
```
doc1.md: rerank_score=6.5924
doc2.md: rerank_score=-11.1473
```

---

## Configuration

### Environment Variables

**L4_RERANK_MODEL** (future feature)
```bash
export L4_RERANK_MODEL="cross-encoder/ms-marco-MiniLM-L-12-v2"
```

Currently uses hardcoded `cross-encoder/ms-marco-MiniLM-L-6-v2`.

### Model Selection

Available cross-encoder models (future):

| Model | Parameters | Speed | Accuracy |
|-------|-----------|-------|----------|
| ms-marco-MiniLM-L-6-v2 | 23M | Fast | Good |
| ms-marco-MiniLM-L-12-v2 | 33M | Medium | Better |
| ms-marco-electra-base | 110M | Slow | Best |

---

## How It Works

### 1. Input Processing

Reranking receives top-20 results after RRF fusion:

```python
merged = rrf_merge(
    ("fts", fts_results),
    ("semantic", semantic_results),
    ("bm25", bm25_results)
)

# Take top-20 for reranking
candidates = merged[:20]
```

### 2. Text Extraction

For each candidate, extract the best snippet:

```python
for result in candidates:
    # Use first available source
    for source_list in result.sources.values():
        if source_list:
            text = source_list[0].get("snippet", "")
            break
```

### 3. Cross-Encoder Scoring

Process query-document pairs:

```python
pairs = [(query, text) for text in texts]
scores = model.predict(pairs)  # Neural network inference
```

### 4. Reordering

Sort by cross-encoder scores:

```python
for result, score in zip(candidates, scores):
    result.rerank_score = float(score)

candidates.sort(key=lambda x: x.rerank_score, reverse=True)
```

---

## Performance Analysis

### Timing Breakdown

**Typical execution (15 results):**
```
Model loading:     ~1000ms  (first import only)
Text extraction:      ~1ms
Cross-encoder:      ~300ms  (15 pairs)
Sorting:             <1ms
─────────────────────────────
Total:              ~301ms
```

### Impact on Results

**Before reranking (RRF scores):**
```
[1] decisions.md       score=0.0328  (RRF rank 1)
[2] README.md          score=0.0323  (RRF rank 2)
[3] handoff.md         score=0.0317  (RRF rank 3)
```

**After reranking (cross-encoder scores):**
```
[1] feedback.md        rerank=4.9216  (was rank 7)
[2] feedback.md        rerank=1.5606  (was rank 5)
[3] README.md          rerank=-0.9046 (was rank 2)
```

**Changes:** 10/10 positions changed in top-10

### Accuracy Improvement

Cross-encoder reranking typically improves:
- **NDCG@10:** +5-15% over RRF alone
- **MRR:** +10-20% (first relevant result appears earlier)
- **Precision@5:** +15-25% (more relevant results in top-5)

---

## Graceful Degradation

Reranking is designed to fail gracefully:

### Model Not Loaded

```python
if _model is None:
    return candidates  # Return unchanged
```

**Behavior:** Search continues without reranking, no error.

### Prediction Failure

```python
try:
    scores = _model.predict(pairs)
except Exception as exc:
    logging.warning("Cross-encoder prediction failed: %s", exc)
    return candidates  # Return unchanged
```

**Behavior:** Logs warning, returns original order.

### Missing Snippets

```python
text = source_list[0].get("snippet") or source_list[0].get("text", "")
```

**Behavior:** Uses empty string, model handles gracefully.

---

## Best Practices

### When to Use Reranking

✅ **Use reranking when:**
- Precision matters more than recall
- Top-5 results quality is critical
- Query is specific and well-formed
- You have 10+ candidates to rerank

❌ **Skip reranking when:**
- Speed is critical (<100ms requirement)
- Very few candidates (<5)
- Exploratory broad searches
- Query is very short (1-2 words)

### Optimal Candidate Count

**Recommended:** 15-20 candidates

- **Too few (<10):** Limited reordering benefit
- **Optimal (15-20):** Best accuracy/speed tradeoff
- **Too many (>50):** Diminishing returns, slower

### Query Quality

**Good queries for reranking:**
```
"how to implement cross-encoder reranking"
"memory system architecture decisions"
"semantic search vs keyword search comparison"
```

**Poor queries for reranking:**
```
"memory"           (too broad)
"bug"              (too vague)
"x y z"            (no context)
```

---

## Troubleshooting

### Model Loading Fails

**Symptom:**
```
Failed to load cross-encoder model: ...
```

**Solution:**
```bash
pip install --upgrade sentence-transformers
```

### Slow Performance

**Symptom:** Reranking takes >1s

**Causes:**
1. Too many candidates (>30)
2. Very long snippets (>512 tokens)
3. CPU-only inference

**Solutions:**
1. Reduce candidates to 20
2. Truncate snippets to 200 words
3. Use GPU if available (future feature)

### Unexpected Rankings

**Symptom:** Reranking produces worse results

**Causes:**
1. Poor snippet quality (truncated, no context)
2. Query-document mismatch
3. Model not suited for domain

**Solutions:**
1. Improve chunking strategy
2. Rephrase query
3. Try different model (future feature)

---

## Testing

### Unit Tests

Run reranking tests:

```bash
pytest tests/test_l4_rerank.py -v
```

**Coverage:**
- ✅ Basic reranking functionality
- ✅ Empty candidates handling
- ✅ Model not loaded graceful degradation
- ✅ Score added to sources metadata
- ✅ Sorting by rerank_score
- ✅ Prediction failure handling
- ✅ Missing snippet handling
- ✅ Multiple sources handling
- ✅ Original fields preservation
- ✅ rerank_score field addition

### Integration Tests

Test full pipeline:

```bash
python scripts/l4_fts5_search.py hybrid "test query"
```

**Expected output:**
```
[RERANKING] Applying cross-encoder to top-N results...
[RERANKING] Completed in X.XXXs, Y/10 positions changed in top-10
```

---

## Future Enhancements

### Planned Features

1. **Model Selection via Environment Variable**
   ```bash
   export L4_RERANK_MODEL="cross-encoder/ms-marco-MiniLM-L-12-v2"
   ```

2. **GPU Acceleration**
   - Automatic GPU detection
   - 5-10x faster inference

3. **Batch Size Tuning**
   ```python
   rerank(query, candidates, batch_size=32)
   ```

4. **Domain-Specific Models**
   - Code search: `cross-encoder/code-search`
   - Scientific: `cross-encoder/scibert`

5. **Caching**
   - Cache (query, document) scores
   - LRU cache with 1000 entries

### Not Planned

- ❌ Training custom models (use pretrained)
- ❌ Multi-language models (current model is English-only)
- ❌ Real-time streaming reranking

---

## References

### Papers

1. **Nogueira & Cho (2019):** "Passage Re-ranking with BERT"
   - https://arxiv.org/abs/1901.04085

2. **Cormack et al. (2009):** "Reciprocal Rank Fusion"
   - SIGIR 2009

### Models

- **MS MARCO:** https://microsoft.github.io/msmarco/
- **Sentence Transformers:** https://www.sbert.net/
- **Cross-Encoders:** https://www.sbert.net/examples/applications/cross-encoder/README.html

### Related Documentation

- [Hybrid Search Architecture](../ARCHITECTURE.md)
- [RRF Ranking](../scripts/ranking.py)
- [FTS5 Search](../scripts/l4_fts5_search.py)

---

## Changelog

### 2026-05-07 - v1.0 (Initial Release)

**Added:**
- Cross-encoder reranking implementation
- Integration with hybrid search pipeline
- CLI flag `--no-rerank`
- Performance metrics logging
- Comprehensive test suite (10 tests)
- This documentation

**Model:**
- cross-encoder/ms-marco-MiniLM-L-6-v2

**Performance:**
- ~300ms for 15 candidates
- 10/10 positions changed in top-10 (typical)

---

## License

MIT License - See [LICENSE](../LICENSE) file for details.

---

**Questions or Issues?**

- GitHub Issues: https://github.com/mergelord/claude-4layer-memory/issues
- Documentation: https://github.com/mergelord/claude-4layer-memory
