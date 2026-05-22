#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Benchmark script for comparing sequential vs parallel hybrid search performance.

Usage:
    python benchmark_parallel_search.py <query>
    python benchmark_parallel_search.py "machine learning algorithms"
"""

import sys
import time
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent))

from l4_fts5_search import L4FTS5Search


def benchmark_search(query: str, iterations: int = 5) -> None:
    """
    Run benchmark comparing sequential and parallel hybrid search.
    
    Args:
        query: Search query to test
        iterations: Number of iterations to average
    """
    print("=" * 80)
    print(f"BENCHMARK: Hybrid Search Performance Comparison")
    print(f"Query: '{query}'")
    print(f"Iterations: {iterations}")
    print("=" * 80)
    print()
    
    # Initialize FTS5 search
    fts = L4FTS5Search()
    
    # Warm-up run (not counted)
    print("Warming up...")
    try:
        fts.search(query, limit=20)
    except Exception as e:
        print(f"Warning: Warm-up failed: {e}")
    print()
    
    # Sequential benchmark
    print("Running SEQUENTIAL hybrid search...")
    sequential_times = []
    for i in range(iterations):
        start = time.time()
        try:
            # Import here to avoid circular dependency
            from l4_fts5_search import cmd_hybrid
            
            # Redirect output to suppress search results
            import io
            import contextlib
            
            with contextlib.redirect_stdout(io.StringIO()):
                cmd_hybrid(fts, query, enable_rerank=False)
            
            elapsed = time.time() - start
            sequential_times.append(elapsed)
            print(f"  Iteration {i+1}/{iterations}: {elapsed:.3f}s")
        except Exception as e:
            print(f"  Iteration {i+1}/{iterations}: FAILED - {e}")
    
    print()
    
    # Parallel benchmark
    print("Running PARALLEL hybrid search...")
    parallel_times = []
    for i in range(iterations):
        start = time.time()
        try:
            from l4_fts5_search import cmd_hybrid_parallel
            
            import io
            import contextlib
            
            with contextlib.redirect_stdout(io.StringIO()):
                cmd_hybrid_parallel(fts, query, enable_rerank=False)
            
            elapsed = time.time() - start
            parallel_times.append(elapsed)
            print(f"  Iteration {i+1}/{iterations}: {elapsed:.3f}s")
        except Exception as e:
            print(f"  Iteration {i+1}/{iterations}: FAILED - {e}")
    
    print()
    print("=" * 80)
    print("RESULTS")
    print("=" * 80)
    
    if sequential_times and parallel_times:
        seq_avg = sum(sequential_times) / len(sequential_times)
        seq_min = min(sequential_times)
        seq_max = max(sequential_times)
        
        par_avg = sum(parallel_times) / len(parallel_times)
        par_min = min(parallel_times)
        par_max = max(parallel_times)
        
        speedup = seq_avg / par_avg if par_avg > 0 else 0
        improvement = ((seq_avg - par_avg) / seq_avg * 100) if seq_avg > 0 else 0
        
        print(f"\nSequential (avg): {seq_avg:.3f}s  (min: {seq_min:.3f}s, max: {seq_max:.3f}s)")
        print(f"Parallel (avg):   {par_avg:.3f}s  (min: {par_min:.3f}s, max: {par_max:.3f}s)")
        print()
        print(f"Speedup:      {speedup:.2f}x")
        print(f"Improvement:  {improvement:.1f}%")
        print()
        
        if speedup >= 2.0:
            print("✓ EXCELLENT: Achieved 2x+ speedup!")
        elif speedup >= 1.5:
            print("✓ GOOD: Significant performance improvement")
        elif speedup >= 1.2:
            print("✓ MODERATE: Noticeable improvement")
        else:
            print("⚠ LIMITED: Minimal improvement (check system load)")
    else:
        print("ERROR: Benchmark failed to complete")
    
    print("=" * 80)


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nExample queries:")
        print("  python benchmark_parallel_search.py 'memory system'")
        print("  python benchmark_parallel_search.py 'search algorithm'")
        print("  python benchmark_parallel_search.py 'configuration'")
        sys.exit(1)
    
    query = " ".join(sys.argv[1:])
    
    try:
        benchmark_search(query, iterations=5)
    except KeyboardInterrupt:
        print("\n\nBenchmark interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nBenchmark failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

# Made with Bob
