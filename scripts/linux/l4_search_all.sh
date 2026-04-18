#!/bin/bash
# L4 SEMANTIC - Search across all projects
if [ -z "$1" ]; then
    echo "Usage: l4_search_all.sh \"search query\""
    exit 1
fi
python3 "$HOME/.claude/hooks/l4_semantic_global.py" search-all "$@"
