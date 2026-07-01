"""
Provider registry.

Maps a `config.provider` string (config.json) to the matching provider
module's `build_chat_model(config)` function. See providers/base.py for the
expected shape of a provider module.
"""

from providers.base import BuildChatModel
from providers.llamacpp import build_chat_model as _build_llamacpp_chat_model
from providers.openai import build_chat_model as _build_openai_chat_model

PROVIDERS: dict[str, BuildChatModel] = {
    "openai": _build_openai_chat_model,
    "llamacpp": _build_llamacpp_chat_model,
}

__all__ = ["PROVIDERS"]
