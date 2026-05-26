# Troubleshooting Guide

Common issues and solutions for Claude 4-Layer Memory System.

---

## Table of Contents

- [Installation Issues](#installation-issues)
- [Search Problems](#search-problems)
- [Indexing Issues](#indexing-issues)
- [Memory Lint Errors](#memory-lint-errors)
- [Encoding Problems](#encoding-problems)
- [Performance Issues](#performance-issues)
- [Platform-Specific Issues](#platform-specific-issues)

---

## Installation Issues

### Python Version Error

**Error:**
```
Python 3.10 or higher is required
```

**Solution:**
1. Check Python version:
   ```bash
   python --version
   ```

2. Install Python 3.10+:
   - **Windows:** Download from [python.org](https://www.python.org/downloads/)
   - **Linux:** `sudo apt install python3.10` or `sudo yum install python310`
   - **macOS:** `brew install python@3.10`

3. Verify installation:
   ```bash
   python3.10 --version
   ```

### Pip Install Fails

**Error:**
```
ERROR: Could not install packages due to an OSError
```

**Solutions:**

1. **Permission denied:**
   ```bash
   # Use --user flag
   pip install --user -r requirements.txt
   
   # Or use virtual environment
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   venv\Scripts\activate     # Windows
   pip install -r requirements.txt
   ```

2. **Network issues:**
   ```bash
   # Use different index
   pip install -r requirements.txt --index-url https://pypi.org/simple
   
   # Or increase timeout
   pip install -r requirements.txt --timeout 100
   ```

3. **Outdated pip:**
   ```bash
   python -m pip install --upgrade pip
   ```

### Model Download Fails

**Error:**
```
Failed to download sentence-transformers model
```

**Solutions:**

1. **Check internet connection**

2. **Manual download:**
   ```python
   from sentence_transformers import SentenceTransformer
   model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
   ```

3. **Use cache:**
   ```bash
   # Set cache directory
   export SENTENCE_TRANSFORMERS_HOME=/path/to/cache
   ```

4. **Offline installation:**
   - Download model from [HuggingFace](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)
   - Place in `~/.cache/torch/sentence_transformers/`

---

## Search Problems

### No Results Found

**Symptoms:**
- Search returns empty results
- "No matches found" message

**Diagnosis:**
```bash
# Check index status
python scripts/l4_semantic_global.py stats

# Check collections
python scripts/l4_semantic_global.py list
```

**Solutions:**

1. **Project not indexed:**
   ```bash
   l4_index_all.bat  # Windows
   l4_index_all.sh   # Linux/Mac
   ```

2. **Empty memory files:**
   - Add content to `~/.claude/memory/`
   - Add content to project memory directories

3. **Query too specific:**
   ```bash
   # Try broader terms
   l4_search_all.bat "error"  # Instead of "NullPointerException in UserService.java line 42"
   ```

4. **Wrong collection:**
   ```bash
   # Search all collections
   python scripts/l4_semantic_global.py search "query" --all
   ```

### Collection Not Found Error

**Error:**
```
Collection 'project-name' not found
```

**Solutions:**

1. **Add to GLOBAL_PROJECTS.md:**
   ```markdown
   ### Project Name
   **Path:** `/path/to/project`
   **Memory:** `~/.claude/projects/path-to-project/memory/`
   **Status:** ✅ Active
   ```

2. **Reindex:**
   ```bash
   l4_index_all.bat
   ```

3. **Check collection name:**
   ```bash
   # List all collections
   python scripts/l4_semantic_global.py list
   ```

### Slow Search Performance

**Symptoms:**
- First search takes >30 seconds
- Subsequent searches still slow

**Solutions:**

1. **First-time model download (normal):**
   - Wait for model download to complete
   - Subsequent searches will be fast

2. **Too many results:**
   ```bash
   # Limit results
   l4_search_all.bat "query" 5  # Top 5 only
   ```

3. **Large collections:**
   ```bash
   # Use parallel search (default)
   python scripts/l4_semantic_global.py search "query" --parallel
   ```

4. **Disable reranking for speed:**
   ```python
   # In l4_semantic_global.py
   USE_RERANKING = False
   ```

---

## Indexing Issues

### Indexing Fails

**Error:**
```
Failed to index directory: [path]
```

**Solutions:**

1. **Permission denied:**
   ```bash
   # Check directory permissions
   ls -la /path/to/memory
   
   # Fix permissions
   chmod -R 755 ~/.claude/memory
   ```

2. **Invalid path:**
   ```bash
   # Verify path exists
   ls /path/to/project
   
   # Use absolute paths in GLOBAL_PROJECTS.md
   ```

3. **Corrupted files:**
   ```bash
   # Validate encoding
   python scripts/memory_lint.py --validate-encoding
   
   # Repair if needed
   python scripts/memory_lint.py --repair-mojibake --apply
   ```

### System Artifacts Indexed

**Symptoms:**
- Collections like `C--WINDOWS-system32`
- Unwanted system directories indexed

**Solutions:**

1. **Run cleanup:**
   ```bash
   python scripts/cleanup_system_artifacts.py
   ```

2. **Update .gitignore patterns:**
   ```bash
   # Add to memory/.gitignore
   **/node_modules/
   **/.git/
   **/venv/
   ```

3. **Manual cleanup:**
   ```bash
   python scripts/l4_semantic_global.py cleanup --dry-run
   python scripts/l4_semantic_global.py cleanup
   ```

### Out of Memory During Indexing

**Error:**
```
MemoryError: Unable to allocate array
```

**Solutions:**

1. **Index in batches:**
   ```bash
   # Index one project at a time
   python scripts/l4_semantic_global.py index /path/to/project1
   python scripts/l4_semantic_global.py index /path/to/project2
   ```

2. **Reduce chunk size:**
   ```python
   # In chunking.py
   MAX_CHUNK_SIZE = 500  # Reduce from 1000
   ```

3. **Close other applications**

4. **Increase swap space (Linux):**
   ```bash
   sudo fallocate -l 4G /swapfile
   sudo chmod 600 /swapfile
   sudo mkswap /swapfile
   sudo swapon /swapfile
   ```

---

## Memory Lint Errors

### Ghost Links Detected

**Error:**
```
[X] Found 5 ghost link(s)
```

**Solutions:**

1. **Update links:**
   ```markdown
   <!-- Old -->
   [See details](./old-file.md)
   
   <!-- New -->
   [See details](./new-file.md)
   ```

2. **Remove broken links:**
   ```bash
   # Find all ghost links
   python scripts/memory_lint.py --layer 1
   ```

3. **Auto-fix (if available):**
   ```bash
   python scripts/memory_lint.py --fix-links
   ```

### Old HOT Memory Entries

**Error:**
```
[X] 3 HOT entries older than 24h
```

**Solutions:**

1. **Archive old entries:**
   ```bash
   # Move to WARM layer
   mv ~/.claude/memory/handoff.md ~/.claude/memory/decisions.md
   ```

2. **Update timestamps:**
   ```markdown
   ---
   date: 2026-05-22  # Update to current date
   ---
   ```

3. **Auto-rotate:**
   ```bash
   python scripts/health_memory_size.py --rotate
   ```

### Large File Warning

**Error:**
```
[X] 2 file(s) exceed 100KB limit
```

**Solutions:**

1. **Split large files:**
   ```bash
   # Split by topic
   decisions.md → decisions-api.md, decisions-ui.md
   ```

2. **Archive old content:**
   ```bash
   # Move to archive/
   mv large-file.md ~/.claude/memory/archive/2026-04/
   ```

3. **Compress content:**
   - Remove redundant information
   - Use links instead of duplicating content

---

## Encoding Problems

### Mojibake (Corrupted Cyrillic Text)

**Symptoms:**
```
РџСЂРёРІРµС‚  # Should be: Привет
```

**Diagnosis:**
```bash
# Scan for issues
python scripts/memory_lint.py --validate-encoding
```

**Solutions:**

1. **Auto-repair:**
   ```bash
   # Preview fixes
   python scripts/memory_lint.py --repair-mojibake
   
   # Apply fixes
   python scripts/memory_lint.py --repair-mojibake --apply
   ```

2. **Manual fix:**
   ```python
   # In Python
   text = "РџСЂРёРІРµС‚"
   fixed = text.encode('latin1').decode('utf-8')
   print(fixed)  # Привет
   ```

3. **Prevent future issues:**
   ```bash
   # Set console encoding (Windows)
   chcp 65001
   
   # Or use EncodingGate hook
   # (automatically installed)
   ```

### UnicodeDecodeError

**Error:**
```
UnicodeDecodeError: 'utf-8' codec can't decode byte
```

**Solutions:**

1. **Check file encoding:**
   ```bash
   file -i filename.md
   ```

2. **Convert to UTF-8:**
   ```bash
   # Linux/Mac
   iconv -f ISO-8859-1 -t UTF-8 file.md > file_utf8.md
   
   # Windows
   Get-Content file.md | Set-Content -Encoding UTF8 file_utf8.md
   ```

3. **Use EncodingGate:**
   ```bash
   python scripts/memory_lint.py --repair-mojibake --apply
   ```

---

## Performance Issues

### High CPU Usage

**Symptoms:**
- CPU at 100% during search
- System becomes unresponsive

**Solutions:**

1. **Limit parallel workers:**
   ```python
   # In l4_semantic_global.py
   MAX_WORKERS = 2  # Reduce from 4
   ```

2. **Use quick mode:**
   ```bash
   python scripts/memory_lint.py --quick
   ```

3. **Reduce result count:**
   ```bash
   l4_search_all.bat "query" 3  # Top 3 only
   ```

### High Memory Usage

**Symptoms:**
- RAM usage >4GB
- System swapping

**Solutions:**

1. **Clear cache:**
   ```python
   from l4_semantic_global import GlobalSemanticMemory
   memory = GlobalSemanticMemory()
   memory.clear_cache()
   ```

2. **Reduce batch size:**
   ```python
   # In l4_semantic_global.py
   BATCH_SIZE = 16  # Reduce from 32
   ```

3. **Close unused applications**

### Slow Disk I/O

**Symptoms:**
- Indexing takes >10 minutes
- High disk usage

**Solutions:**

1. **Use SSD if available**

2. **Exclude large directories:**
   ```markdown
   # In GLOBAL_PROJECTS.md
   **Exclude:** node_modules/, .git/, build/
   ```

3. **Optimize ChromaDB:**
   ```python
   # In l4_semantic_global.py
   settings = Settings(
       anonymized_telemetry=False,
       allow_reset=True,
       is_persistent=True
   )
   ```

---

## Platform-Specific Issues

### Windows

#### PowerShell Execution Policy

**Error:**
```
cannot be loaded because running scripts is disabled
```

**Solution:**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

#### Path Too Long

**Error:**
```
The specified path, file name, or both are too long
```

**Solution:**
1. Enable long paths:
   ```powershell
   # Run as Administrator
   New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
   ```

2. Use shorter project names in GLOBAL_PROJECTS.md

#### Console Encoding

**Issue:** Cyrillic text displays incorrectly

**Solution:**
```cmd
chcp 65001
```

Add to startup script or use EncodingGate (automatic).

### Linux

#### Permission Denied

**Error:**
```
PermissionError: [Errno 13] Permission denied
```

**Solution:**
```bash
# Fix permissions
chmod +x install.sh
chmod +x scripts/linux/*.sh

# Or run with sudo (not recommended)
sudo ./install.sh
```

#### Missing Dependencies

**Error:**
```
ModuleNotFoundError: No module named 'sqlite3'
```

**Solution:**
```bash
# Ubuntu/Debian
sudo apt-get install python3-dev libsqlite3-dev

# CentOS/RHEL
sudo yum install python3-devel sqlite-devel

# Reinstall Python
python -m pip install --upgrade --force-reinstall sqlite3
```

### macOS

#### Gatekeeper Blocks Execution

**Error:**
```
"install.sh" cannot be opened because it is from an unidentified developer
```

**Solution:**
```bash
# Remove quarantine attribute
xattr -d com.apple.quarantine install.sh

# Or allow in System Preferences
# System Preferences → Security & Privacy → Allow
```

#### Homebrew Python Issues

**Issue:** Multiple Python versions conflict

**Solution:**
```bash
# Use specific Python version
python3.10 -m pip install -r requirements.txt

# Or create alias
alias python=python3.10
```

---

## Getting Help

If you can't resolve your issue:

1. **Check logs:**
   ```bash
   # Enable debug logging
   export DEBUG=1
   python scripts/l4_semantic_global.py search "query"
   ```

2. **Run diagnostics:**
   ```bash
   python audit.py
   ```

3. **Search existing issues:**
   - [GitHub Issues](https://github.com/mergelord/claude-4layer-memory/issues)

4. **Create new issue:**
   - Include error messages
   - Include system info (OS, Python version)
   - Include steps to reproduce

5. **Community support:**
   - [GitHub Discussions](https://github.com/mergelord/claude-4layer-memory/discussions)

---

**Last Updated:** 2026-05-22  
**Version:** 1.4.0