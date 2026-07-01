# Smart AI Agent

A ReAct + Retrieval-Augmented Generation (RAG) agent built with LangGraph and ChromaDB.
It retrieves information from internal Markdown documents and supports both cloud (OpenAI) and fully local (llama.cpp) inference.

---

## Key Features

- ReAct + RAG architecture via LangGraph
- Internal vector database powered by ChromaDB
- Persistent agent memory (read/write)
- Conversation history window
- Built-in tools: date/time, math, KB queries, memory management
- **Two inference modes**: OpenAI API or any local OpenAI-compatible server (llama.cpp, Ollama, LM Studio)
- **Two embedding modes**: OpenAI embeddings or local HuggingFace sentence-transformers (no API key required)

---

## Prerequisites

- Python `>=3.12`
- [Poetry](https://python-poetry.org/)
- **OpenAI mode**: an OpenAI API key
- **Local mode**: a running [llama.cpp server](https://github.com/ggerganov/llama.cpp) or compatible runtime

---

## Quick Setup

```bash
# 1. Create and activate a conda environment
conda create -n langchain-python3.13 python=3.13
conda activate langchain-python3.13

# 2. Install Poetry
conda install -c conda-forge poetry poetry-plugin-export

# 3. Disable Poetry's own virtualenv (using conda's instead)
poetry config virtualenvs.create false

# 4. Install dependencies
poetry install
```

### Update dependencies

```bash
poetry show --outdated
poetry update
poetry export -f requirements.txt --output requirements.txt --without-hashes
```

---

## Configuration

All settings live in `config.json`. Two example files are provided:

| File | Purpose |
|---|---|
| `config.example.openai.json` | Example template for OpenAI mode |
| `config.example.llamacpp.json` | Example template for llama.cpp mode |
| `config.json` | Active configuration (edit this one) |

### Configuration reference

```jsonc
{
  // Active LLM provider: "openai" or "llamacpp"
  "provider": "openai",

  // OpenAI provider settings (used when provider = "openai")
  "openai": {
    "model": "gpt-5-mini",
    "base_url": null,           // optional: point to any OpenAI-compatible server
    "api_key_env": "OPENAI_API_KEY"
  },

  // Local provider settings (used when provider = "llamacpp")
  "llamacpp": {
    "model": "local-model",
    "base_url": "http://localhost:5000/v1",
    "extra_body": null          // optional: extra fields sent in every request body
  },

  "vectordb": {
    // Embedding provider: "openai" or "huggingface"
    "embedding_provider": "openai",
    "embedding_name": "text-embedding-3-small",
    "embedding_base_url": null, // optional: point OpenAI embeddings to a local server
    "embedding_api_key_env": "OPENAI_API_KEY",
    "docs_path": "../../assets/docs",
    "docs_glob": "**/*.md",
    "db_path": "../../assets/chroma_db",
    "collection_name": "internal_kb"
  },

  "agent": {
    "memory_path": "../../assets/bot_memory.json",
    "history_window": 10
  }
}
```

---

## Mode A — OpenAI (cloud)

Everything runs on OpenAI's infrastructure. Simplest setup, highest accuracy.

**`config.json`**:
```json
{
  "provider": "openai",
  "openai": {
    "model": "gpt-5-mini",
    "base_url": null,
    "api_key_env": "OPENAI_API_KEY"
  },
  "vectordb": {
    "embedding_provider": "openai",
    "embedding_name": "text-embedding-3-small",
    "docs_path": "../../assets/docs",
    "docs_glob": "**/*.md",
    "db_path": "../../assets/chroma_db",
    "collection_name": "internal_kb"
  },
  "agent": {
    "memory_path": "../assets/bot_memory.json",
    "history_window": 10
  }
}
```

**`.env`**:
```text
OPENAI_API_KEY=sk-...
```

**Recommended models**: `gpt-5-mini` (fast, cheap), `gpt-5.4` (best quality).

See [OpenAI Models docs](https://developers.openai.com/api/docs/models) for the list of available models and their capabilities.

---

## Mode B — Fully local (llama.cpp)

The LLM runs locally on your machine. No data leaves your network. Embeddings can also run locally.

### 1. Start the local LLM server

Any OpenAI-compatible runtime works. Example with **llama.cpp server** and
[Qwen3.5-35B-A3B](https://unsloth.ai/docs/models/qwen3.5):

```bash
llama-server \
  -hf unsloth/Qwen3.5-35B-A3B-GGUF:UD-Q4_K_XL \
  --ctx-size 16384 \
  --temp 1.0 --top-p 0.95 --top-k 20 --min-p 0.00 \
  --chat-template-kwargs "{\"enable_thinking\": false}" \
  --port 5000 \
  --jinja
```

> **Note:** Do **not** use the `--special` flag — it causes Qwen3's Jinja template to misplace
> `<|im_end|>` tokens when tool calling is active, resulting in a server 500 error.

### 2. Choose an embedding strategy

Since the local LLM server typically does not serve embeddings, pick one of the options below.

#### Option B1 — HuggingFace embeddings (fully offline, recommended)

Runs entirely on CPU/GPU, no API key needed.
`sentence-transformers/all-MiniLM-L6-v2` is a good general-purpose choice (384-dim, fast).

```json
"vectordb": {
  "embedding_provider": "huggingface",
  "embedding_name": "sentence-transformers/all-MiniLM-L6-v2",
  "docs_path": "../../assets/docs",
  "docs_glob": "**/*.md",
  "db_path": "../../assets/chroma_db",
  "collection_name": "internal_kb"
}
```

#### Option B2 — OpenAI embeddings (hybrid)

The LLM stays local; only the embedding calls go to OpenAI.
Useful when you want the best retrieval quality without running a separate embedding server.

```json
"vectordb": {
  "embedding_provider": "openai",
  "embedding_name": "text-embedding-3-small",
  "docs_path": "../../assets/docs",
  "docs_glob": "**/*.md",
  "db_path": "../../assets/chroma_db",
  "collection_name": "internal_kb"
}
```

Requires `OPENAI_API_KEY` in `.env`.

#### Option B3 — Local OpenAI-compatible embedding server

Point the embedding client to any server exposing `/v1/embeddings`
(e.g. Ollama with `nomic-embed-text`, text-embeddings-inference, etc.).

```json
"vectordb": {
  "embedding_provider": "openai",
  "embedding_name": "nomic-embed-text",
  "embedding_base_url": "http://localhost:11434/v1",
  "docs_path": "../../assets/docs",
  "docs_glob": "**/*.md",
  "db_path": "../../assets/chroma_db",
  "collection_name": "internal_kb"
}
```

No API key required.

### 3. Full local config example

```json
{
  "provider": "llamacpp",
  "llamacpp": {
    "model": "local-model",
    "base_url": "http://localhost:5000/v1"
  },
  "vectordb": {
    "embedding_provider": "huggingface",
    "embedding_name": "sentence-transformers/all-MiniLM-L6-v2",
    "docs_path": "../../assets/docs",
    "docs_glob": "**/*.md",
    "db_path": "../../assets/chroma_db",
    "collection_name": "internal_kb"
  },
  "agent": {
    "memory_path": "../assets/bot_memory.json",
    "history_window": 10
  }
}
```

No `.env` file needed for this setup.

---

## Environment Variables

Copy `.env.example` to `.env` and fill in what you need:

```text
# Required for OpenAI provider or OpenAI embeddings
OPENAI_API_KEY=sk-...

# Optional: LangSmith tracing (see section below)
# LANGSMITH_TRACING=true
# LANGSMITH_ENDPOINT=https://api.smith.langchain.com
# LANGSMITH_API_KEY=lsv2_...
# LANGSMITH_PROJECT=ai-agent
```

> Never commit `.env` to version control.

---

## Running the Agent

```bash
python main.py
```

Example session:

```text
🤖 Welcome to the AI Agent. You can ask questions about the loaded documents.

Type 'exit' or 'quit' to end the conversation.

🧑‍💻 You: Can you tell me the auth code for the 28 January 2025 meeting?
🤖 Querying the agent

🛠️ Agent decided to use tool: query_kb_tool
🔧 Initializing the vector database retriever...
🔍 Searching internal KB for: auth code 28 January 2025 meeting

🤖 Agent: The auth code for the meeting on 28 January 2025 is **42**.
          It runs from 3:00 PM to 4:00 PM via Microsoft Teams.

🧑‍💻 You: exit
Exiting the conversation. Goodbye!
```

---

## Example Queries

Try these sample queries:

- **Meeting details:**
  *Can you tell me the auth code for the 28 January 2025 meeting?*
  → Searches the internal knowledge base for relevant info.

- **Personalized responses:**
  *What's my lucky number?*
  → Uses conversation memory or context for a response.

Feel free to experiment with questions related to your documentation or general queries!

---

## Available Tools

| Tool | Description |
|---|---|
| `query_kb_tool` | Semantic search over the ChromaDB knowledge base |
| `get_memory_tool` | Reads the agent's persistent memory |
| `update_memory_tool` | Updates the agent's persistent memory |
| `get_today_date` | Returns today's date |
| `get_current_time` | Returns the current time |
| `calculate` | Evaluates mathematical expressions (via `numexpr`) |

---

## Observability: LangSmith

Add these variables to `.env` to enable tracing:

```text
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=ai-agent
```

---

## Supported Models

This agent has been tested with and supports **Qwen3.5**, Alibaba's latest MoE language model family.
See the [official Qwen3.5 documentation](https://unsloth.ai/docs/models/qwen3.5) for details on available variants and quantizations.

### Running Qwen3.5 locally with llama.cpp

```bash
llama-server \
  -hf unsloth/Qwen3.5-35B-A3B-GGUF:UD-Q4_K_XL \
  --ctx-size 16384 \
  --temp 1.0 --top-p 0.95 --top-k 20 --min-p 0.00 \
  --chat-template-kwargs "{\"enable_thinking\": false}" \
  --port 5000 \
  --jinja
```

Then point the agent at `http://localhost:5000/v1` using the `llamacpp` provider (see [Mode B](#mode-b--fully-local-llamacpp) above).

---

## License

This project is licensed under a **No-Commercial License** (see LICENSE file).
It depends on third-party libraries that allow free use for personal, experimental, or research purposes, but may restrict commercial use.
