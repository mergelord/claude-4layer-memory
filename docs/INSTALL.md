# Installation Guide

Complete installation instructions for Claude 4-Layer Memory System.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Installation](#quick-installation)
- [Manual Installation](#manual-installation)
- [Verification](#verification)
- [Troubleshooting](#troubleshooting)
- [Uninstallation](#uninstallation)

---

## Prerequisites

### Required

- **Python 3.7 or higher**
  - Check: `python --version` or `python3 --version`
  - Download: https://www.python.org/downloads/

- **Claude Code CLI**
  - Must be installed and configured
  - Directory `~/.claude` should exist

- **500MB free disk space**
  - For embeddings model (downloaded automatically)

### Optional

- **Git** (for cloning repository)
- **Virtual environment** (recommended for Python packages)

---

## Quick Installation

### Windows

1. Download or clone the repository
2. Open Command Prompt or PowerShell
3. Navigate to the repository directory
4. Run the installation script:

```cmd
install.bat
```

### Linux / macOS

1. Download or clone the repository
2. Open Terminal
3. Navigate to the repository directory
4. Make the script executable and run:

```bash
chmod +x install.sh
./install.sh
```

The script will:
- ✅ Check Python installation
- ✅ Install dependencies (chromadb, sentence-transformers)
- ✅ Create directory structure
- ✅ Copy scripts to `~/.claude/hooks/`
- ✅ Create configuration templates
- ✅ Initialize memory structure
- ✅ Test the installation

---

## Manual Installation

If you prefer manual installation or the automatic script fails:

### Step 1: Install Python Dependencies

```bash
pip install chromadb sentence-transformers
```

Or with Python 3 explicitly:

```bash
pip3 install chromadb sentence-transformers
```

### Step 2: Create Directory Structure

**Windows:**
```cmd
mkdir %USERPROFILE%\.claude\hooks
mkdir %USERPROFILE%\.claude\memory
mkdir %USERPROFILE%\.claude\memory\archive
mkdir %USERPROFILE%\.claude\memory\outputs
```

**Linux/macOS:**
```bash
mkdir -p ~/.claude/hooks
mkdir -p ~/.claude/memory/archive
mkdir -p ~/.claude/memory/outputs
```

### Step 3: Copy Scripts

**Windows:**
```cmd
copy scripts\l4_semantic_global.py %USERPROFILE%\.claude\hooks\
copy scripts\windows\*.bat %USERPROFILE%\.claude\hooks\
```

**Linux/macOS:**
```bash
cp scripts/l4_semantic_global.py ~/.claude/hooks/
cp scripts/linux/*.sh ~/.claude/hooks/
chmod +x ~/.claude/hooks/*.sh
chmod +x ~/.claude/hooks/l4_semantic_global.py
```

### Step 4: Create Configuration Files

**Windows:**
```cmd
copy templates\GLOBAL_PROJECTS.md.template %USERPROFILE%\.claude\GLOBAL_PROJECTS.md
copy templates\MEMORY.md.template %USERPROFILE%\.claude\memory\MEMORY.md
copy templates\handoff.md.template %USERPROFILE%\.claude\memory\handoff.md
copy templates\decisions.md.template %USERPROFILE%\.claude\memory\decisions.md
```

**Linux/macOS:**
```bash
cp templates/GLOBAL_PROJECTS.md.template ~/.claude/GLOBAL_PROJECTS.md
cp templates/MEMORY.md.template ~/.claude/memory/MEMORY.md
cp templates/handoff.md.template ~/.claude/memory/handoff.md
cp templates/decisions.md.template ~/.claude/memory/decisions.md
```

---

## Verification

### Test L4 SEMANTIC

**Windows:**
```cmd
python %USERPROFILE%\.claude\hooks\l4_semantic_global.py stats
```

**Linux/macOS:**
```bash
python3 ~/.claude/hooks/l4_semantic_global.py stats
```

**Expected output:**
```
[INFO] Loading embedding model: paraphrase-multilingual-MiniLM-L12-v2
[STATS] L4 SEMANTIC Global Statistics:
   DB path: /home/user/.claude/semantic_db_global
   Total collections: 1
   
   Collections:
      memory_global: 0 chunks
         Global memory - knowledge applicable to all projects
```

### Test Batch/Shell Scripts

**Windows:**
```cmd
l4_stats.bat
```

**Linux/macOS:**
```bash
l4_stats.sh
```

---

## Troubleshooting

### Python not found

**Error:** `python: command not found`

**Solution:**
- Install Python 3.7+ from https://www.python.org/
- On Linux/macOS, try `python3` instead of `python`
- Ensure Python is in your PATH

### pip install fails

**Error:** `ERROR: Could not find a version that satisfies the requirement chromadb`

**Solution:**
- Update pip: `pip install --upgrade pip`
- Try with Python 3 explicitly: `pip3 install chromadb sentence-transformers`
- Use virtual environment:
  ```bash
  python -m venv venv
  source venv/bin/activate  # Linux/Mac
  venv\Scripts\activate     # Windows
  pip install chromadb sentence-transformers
  ```

### Claude Code directory not found

**Error:** `Claude Code directory not found`

**Solution:**
- Install Claude Code CLI first
- Verify `~/.claude` directory exists
- Run Claude Code at least once to initialize

### Permission denied (Linux/macOS)

**Error:** `Permission denied: './install.sh'`

**Solution:**
```bash
chmod +x install.sh
./install.sh
```

### Model download fails

**Error:** `Failed to download model`

**Solution:**
- Check internet connection
- Model is ~500MB, ensure sufficient bandwidth
- Try manual download:
  ```python
  from sentence_transformers import SentenceTransformer
  model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
  ```

### Scripts not found after installation

**Error:** `l4_stats.bat: command not found`

**Solution:**
- Ensure scripts are in `~/.claude/hooks/`
- Add `~/.claude/hooks/` to PATH, or
- Run with full path: `~/.claude/hooks/l4_stats.sh`

---

## Uninstallation

### Remove Scripts

**Windows:**
```cmd
del %USERPROFILE%\.claude\hooks\l4_*.bat
del %USERPROFILE%\.claude\hooks\l4_semantic_global.py
```

**Linux/macOS:**
```bash
rm ~/.claude/hooks/l4_*.sh
rm ~/.claude/hooks/l4_semantic_global.py
```

### Remove Data (Optional)

**Warning:** This will delete all indexed data!

**Windows:**
```cmd
rmdir /s /q %USERPROFILE%\.claude\semantic_db_global
rmdir /s /q %USERPROFILE%\.claude\memory
```

**Linux/macOS:**
```bash
rm -rf ~/.claude/semantic_db_global
rm -rf ~/.claude/memory
```

### Uninstall Python Packages (Optional)

```bash
pip uninstall chromadb sentence-transformers
```

---

## Next Steps

After successful installation:

1. **Configure Projects**
   - Edit `~/.claude/GLOBAL_PROJECTS.md`
   - Add your projects following the template

2. **Index Projects**
   - Run `l4_index_all.bat` (Windows) or `l4_index_all.sh` (Linux/Mac)

3. **Test Search**
   - Run `l4_search_all.bat "test query"` (Windows)
   - Run `l4_search_all.sh "test query"` (Linux/Mac)

4. **Read Documentation**
   - [Usage Guide](guides/USAGE.md)
   - [Configuration Guide](guides/CONFIGURATION.md)
   - [Architecture Overview](architecture/ARCHITECTURE.md)

---

## Support

- **Issues:** https://github.com/yourusername/claude-4layer-memory/issues
- **Discussions:** https://github.com/yourusername/claude-4layer-memory/discussions
- **Documentation:** https://yourusername.github.io/claude-4layer-memory

---

**Installation complete! Happy coding with Claude 4-Layer Memory System!**
