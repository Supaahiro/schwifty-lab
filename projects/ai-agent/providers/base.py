"""
LLM Provider interface.

Each provider module must expose a module-level `build_chat_model(config)` function
that returns a LangChain-compatible `BaseChatModel` instance. `providers/__init__.py`
collects these into the `PROVIDERS` registry, keyed by the `config.provider` string.

Provider modules:
  - providers/openai.py   — OpenAI cloud API (default)
  - providers/llamacpp.py — Local model via an OpenAI-compatible API server

Embeddings are configured separately in the `vectordb` section and are not
the responsibility of the chat model provider.
"""

from typing import Any, Callable

from langchain_core.language_models import BaseChatModel

# Type alias for the function every provider module must expose.
BuildChatModel = Callable[[Any], BaseChatModel]
