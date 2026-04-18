# Credits and Acknowledgments

This project stands on the shoulders of giants. We are deeply grateful to the following individuals and projects for their innovative ideas and open-source contributions.

---

## 🏆 Original Authors and Inspirations

### qwwiwi - Core Architecture Pioneer

**GitHub:** [@qwwiwi](https://github.com/qwwiwi)

The foundational architecture of this memory system is based on qwwiwi's groundbreaking work on multi-layer memory systems for Claude Code.

#### Repositories and Contributions:

1. **[public-architecture-claude-code](https://github.com/qwwiwi/public-architecture-claude-code)**
   - **Contribution:** 4-layer memory architecture (HOT/WARM/COLD/L4)
   - **What we adopted:** Core concept of temporal memory layers
   - **Impact:** Foundation of our entire system

2. **[architecture-brain-tests](https://github.com/qwwiwi/architecture-brain-tests)**
   - **Contribution:** Testing methodology for memory systems
   - **What we adopted:** HOT memory 24h window concept, rotation testing
   - **Impact:** Reliability and correctness of our rotation system

3. **[edgelab-install](https://github.com/qwwiwi/edgelab-install)**
   - **Contribution:** Best practices for Claude Code setup
   - **What we adopted:** Installation patterns, hook configuration
   - **Impact:** Our installation scripts and setup procedures

4. **[independence-from-ai](https://github.com/qwwiwi/independence-from-ai)**
   - **Contribution:** AgentSkill concept, independence principles
   - **What we adopted:** Separation of concerns, state management
   - **Impact:** Architecture decisions and system design

5. **[second-brain](https://github.com/qwwiwi/second-brain)**
   - **Contribution:** "Second brain" concept for AI assistants
   - **What we adopted:** Knowledge organization principles
   - **Impact:** Memory structure and indexing approach

6. **[token-monitoring](https://github.com/qwwiwi/token-monitoring)**
   - **Contribution:** Token usage tracking system
   - **What we adopted:** Monitoring patterns (not included in this release)
   - **Impact:** Future feature roadmap

7. **[upstream-check](https://github.com/qwwiwi/upstream-check)**
   - **Contribution:** Automated upstream repository monitoring
   - **What we adopted:** Update checking patterns (not included in this release)
   - **Impact:** Maintenance workflow ideas

---

### cablate - Atomic Knowledge Systems

**GitHub:** [@cablate](https://github.com/cablate)

#### Repositories and Contributions:

1. **[llm-atomic-wiki](https://github.com/cablate/llm-atomic-wiki)**
   - **Contribution:** Atomic wiki system for LLMs
   - **What we adopted:** Principles of atomic knowledge storage, indexing strategies
   - **Impact:** Memory file organization and MEMORY.md index structure

---

## 🔨 This Implementation

### MYRIG - Integration and Extensions

**Contributions to this project:**

1. **L4 SEMANTIC Layer**
   - Semantic search with ChromaDB and sentence-transformers
   - Multilingual support (50+ languages)
   - Auto-discovery of projects
   - Whitelist filtering and cleanup mechanisms

2. **Dual-Level Memory System**
   - Global memory (cross-project knowledge)
   - Project memory (project-specific details)
   - Automatic routing between levels

3. **Auto-Discovery System**
   - GLOBAL_PROJECTS.md parsing
   - Fallback structure-based detection
   - Smart filtering (system directories, temp CWD)

4. **Cross-Platform Support**
   - Windows batch scripts
   - Linux/Mac shell scripts
   - Unified Python core

5. **Health Monitoring**
   - Automatic rotation checks
   - Memory size monitoring
   - Corruption detection

6. **Documentation and Packaging**
   - Comprehensive guides
   - Installation scripts
   - Example configurations

---

## 🌟 Technology Stack

### Core Technologies

- **[ChromaDB](https://www.trychroma.com/)** - Vector database for semantic search
- **[sentence-transformers](https://www.sbert.net/)** - Multilingual embeddings
- **[HuggingFace](https://huggingface.co/)** - Model hosting and distribution

### Embedding Model

- **[paraphrase-multilingual-MiniLM-L12-v2](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2)**
  - Authors: Nils Reimers and Iryna Gurevych
  - License: Apache 2.0
  - Purpose: Multilingual semantic embeddings

---

## 🤝 Community

### Claude Code Community

Special thanks to the Claude Code community for:
- Testing and feedback
- Feature requests and bug reports
- Documentation improvements
- Sharing use cases and workflows

---

## 📜 License Compatibility

All upstream projects used in this work are licensed under permissive open-source licenses:

- **qwwiwi repositories:** MIT License (assumed, verify with author)
- **cablate/llm-atomic-wiki:** MIT License (assumed, verify with author)
- **ChromaDB:** Apache 2.0
- **sentence-transformers:** Apache 2.0
- **This project:** MIT License

---

## 🙏 Thank You

To everyone who contributed ideas, code, documentation, or feedback - thank you for making this project possible.

If we missed anyone or any project that influenced this work, please open an issue or pull request to update this file.

---

## 📧 Contact

For questions about credits or to report missing attributions:
- Open an issue: [GitHub Issues](https://github.com/yourusername/claude-4layer-memory/issues)
- Start a discussion: [GitHub Discussions](https://github.com/yourusername/claude-4layer-memory/discussions)

---

**Last Updated:** 2026-04-18
