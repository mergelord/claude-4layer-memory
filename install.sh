#!/bin/bash
# Claude 4-Layer Memory System - Linux/Mac Installation Script
# Copyright (c) 2026 MYRIG and Contributors
# Licensed under MIT License

set -e

echo "========================================"
echo "Claude 4-Layer Memory System"
echo "Installation Script for Linux/macOS"
echo "========================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Python installation
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}[ERROR]${NC} Python 3 is not installed"
    echo "Please install Python 3.7+ first"
    exit 1
fi

echo -e "${GREEN}[OK]${NC} Python found"
python3 --version

# Check Claude Code installation
if [ ! -d "$HOME/.claude" ]; then
    echo -e "${RED}[ERROR]${NC} Claude Code directory not found"
    echo "Please install Claude Code first"
    exit 1
fi

echo -e "${GREEN}[OK]${NC} Claude Code directory found"

# Install Python dependencies
echo ""
echo "Installing Python dependencies..."
pip3 install chromadb sentence-transformers || {
    echo -e "${RED}[ERROR]${NC} Failed to install dependencies"
    exit 1
}

echo -e "${GREEN}[OK]${NC} Dependencies installed"

# Create directories
echo ""
echo "Creating directory structure..."
mkdir -p "$HOME/.claude/hooks"
mkdir -p "$HOME/.claude/memory/archive"
mkdir -p "$HOME/.claude/memory/outputs"

echo -e "${GREEN}[OK]${NC} Directories created"

# Copy scripts
echo ""
echo "Copying scripts..."
cp -f scripts/l4_semantic_global.py "$HOME/.claude/hooks/"
chmod +x "$HOME/.claude/hooks/l4_semantic_global.py"

cp -f scripts/linux/*.sh "$HOME/.claude/hooks/"
chmod +x "$HOME/.claude/hooks/"*.sh

cp -f hooks/git-activity-detector.py "$HOME/.claude/hooks/"
cp -f hooks/stop_handoff_universal.py "$HOME/.claude/hooks/"
chmod +x "$HOME/.claude/hooks/git-activity-detector.py"
chmod +x "$HOME/.claude/hooks/stop_handoff_universal.py"

echo -e "${GREEN}[OK]${NC} Scripts copied"

# Copy templates
echo ""
echo "Creating configuration templates..."
if [ ! -f "$HOME/.claude/GLOBAL_PROJECTS.md" ]; then
    cp templates/GLOBAL_PROJECTS.md.template "$HOME/.claude/GLOBAL_PROJECTS.md"
    echo -e "${GREEN}[OK]${NC} GLOBAL_PROJECTS.md created"
else
    echo -e "${YELLOW}[SKIP]${NC} GLOBAL_PROJECTS.md already exists"
fi

# Initialize memory structure
echo ""
echo "Initializing memory structure..."
if [ ! -f "$HOME/.claude/memory/MEMORY.md" ]; then
    cp templates/MEMORY.md.template "$HOME/.claude/memory/MEMORY.md"
    echo -e "${GREEN}[OK]${NC} MEMORY.md created"
else
    echo -e "${YELLOW}[SKIP]${NC} MEMORY.md already exists"
fi

if [ ! -f "$HOME/.claude/memory/handoff.md" ]; then
    cp templates/handoff.md.template "$HOME/.claude/memory/handoff.md"
    echo -e "${GREEN}[OK]${NC} handoff.md created"
else
    echo -e "${YELLOW}[SKIP]${NC} handoff.md already exists"
fi

if [ ! -f "$HOME/.claude/memory/decisions.md" ]; then
    cp templates/decisions.md.template "$HOME/.claude/memory/decisions.md"
    echo -e "${GREEN}[OK]${NC} decisions.md created"
else
    echo -e "${YELLOW}[SKIP]${NC} decisions.md already exists"
fi

# Test installation
echo ""
echo "Testing installation..."
if python3 "$HOME/.claude/hooks/l4_semantic_global.py" stats &> /dev/null; then
    echo -e "${GREEN}[OK]${NC} L4 SEMANTIC is working"
else
    echo -e "${YELLOW}[WARN]${NC} L4 SEMANTIC test failed - this is normal on first run"
fi

echo ""
echo "========================================"
echo "Installation Complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Edit ~/.claude/GLOBAL_PROJECTS.md to add your projects"
echo "2. Run: l4_index_all.sh to index your projects"
echo "3. Run: l4_search_all.sh \"query\" to search"
echo ""
echo "Documentation: docs/INSTALL.md"
echo "Usage guide: docs/guides/USAGE.md"
echo ""
