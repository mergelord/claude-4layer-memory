#!/bin/bash
# Memory Lint - Linux/Mac wrapper
# Validates memory structure and content

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEMORY_LINT="$SCRIPT_DIR/../memory_lint.py"

# Default to global memory if no path provided
if [ -z "$1" ]; then
    MEMORY_PATH="$HOME/.claude/memory"
else
    MEMORY_PATH="$1"
fi

echo ""
echo "========================================"
echo "Memory Lint System"
echo "========================================"
echo ""
echo "Memory path: $MEMORY_PATH"
echo ""

python3 "$MEMORY_LINT" "$MEMORY_PATH" "$2" "$3" "$4"
