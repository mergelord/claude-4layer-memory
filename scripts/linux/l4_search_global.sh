#!/bin/bash
# L4 SEMANTIC - Search in global memory only
if [ -z "$1" ]; then
    echo "Usage: l4_search_global.sh \"search query\""
    exit 1
fi
python3 "$HOME/.claude/hooks/l4_semantic_global.py" search-global "$@"
