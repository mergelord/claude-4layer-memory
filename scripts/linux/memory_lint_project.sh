#!/bin/bash
# Memory Lint - Check project memory
# Usage: memory_lint_project.sh [project_path]

if [ -z "$1" ]; then
    echo "Usage: memory_lint_project.sh [project_path]"
    echo "Example: memory_lint_project.sh /home/user/projects/my-project"
    exit 1
fi

PROJECT_PATH="$1"

# Convert path to memory directory format
# /home/user/projects/my-project -> home-user-projects-my-project
MEMORY_NAME=$(echo "$PROJECT_PATH" | sed 's/^[/\\]//; s/[/\\:]/-/g')

MEMORY_PATH="$HOME/.claude/projects/$MEMORY_NAME/memory"

if [ ! -d "$MEMORY_PATH" ]; then
    echo "Error: Project memory not found: $MEMORY_PATH"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$SCRIPT_DIR/memory_lint.sh" "$MEMORY_PATH"
