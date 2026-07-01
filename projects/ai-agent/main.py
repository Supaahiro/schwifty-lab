from dotenv import load_dotenv
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage

from agent import build_agent, print_graph
from core.config import Config
from core.vectordb import build_embeddings, vdb_builder
from tools import load_all_tools

# Load secrets from .env (OPENAI_API_KEY, optional LangSmith vars)
load_dotenv()

# Load and validate configuration
cfg = Config.load_from_file("config.json")

# Build the chat model from the configured provider
if cfg.provider == "openai":
    from providers.openai import build_chat_model
    assert cfg.openai is not None  # guaranteed by model_validator
    llm = build_chat_model(cfg.openai)
elif cfg.provider == "llamacpp":
    from providers.llamacpp import build_chat_model
    assert cfg.llamacpp is not None  # guaranteed by model_validator
    llm = build_chat_model(cfg.llamacpp)
else:
    raise ValueError(f"Unknown provider '{cfg.provider}'. Check config.json.")

# Build embeddings (configured independently of the chat model provider)
embeddings = build_embeddings(
    embedding_provider=cfg.vectordb.embedding_provider,
    embedding_name=cfg.vectordb.embedding_name,
    embedding_base_url=cfg.vectordb.embedding_base_url,
    embedding_api_key_env=cfg.vectordb.embedding_api_key_env,
)

# Build the vector DB retriever closure (lazy — no I/O until first query)
retriever_builder = vdb_builder(
    embeddings=embeddings,
    path=str(cfg.vectordb.docs_path),
    glob=cfg.vectordb.docs_glob,
    db_path=str(cfg.vectordb.db_path),
    collection_name=cfg.vectordb.collection_name,
    recreate=False,
)

# Load all agent tools
all_tools = load_all_tools(
    vdb_builder=retriever_builder,
    memory_path=str(cfg.agent.memory_path),
)

# Compile the LangGraph agent
app = build_agent(llm, all_tools)


def _trim_history(messages: list[BaseMessage], window: int) -> list[BaseMessage]:
    """
    Keeps the last `window` messages without splitting a tool-call/ToolMessage pair.

    A ToolMessage is only valid immediately after the AIMessage whose tool_calls
    it answers, so the cut point is walked back until it no longer lands on one.
    """

    if len(messages) <= window:
        return messages

    cut = len(messages) - window
    while cut > 0 and isinstance(messages[cut], ToolMessage):
        cut -= 1

    return messages[cut:]


def main() -> None:
    """Runs the AI agent in an interactive REPL loop."""

    print("🤖 Welcome to the AI Agent. You can ask questions about the loaded documents.\n")
    print_graph(app, "ascii")
    print("\nType 'exit' or 'quit' to end the conversation.")

    conversation_history = []

    while True:
        try:
            user_input = input("\n🧑‍💻 You: ")
        except KeyboardInterrupt:
            user_input = "exit"

        if user_input.lower() in ("exit", "quit"):
            print("\nExiting the conversation. Goodbye!")
            break

        conversation_history.append(HumanMessage(content=user_input))

        result = app.invoke(
            {"messages": _trim_history(conversation_history, cfg.agent.history_window)})
        if not result or "messages" not in result:
            print("🤖 Agent: No response from the agent.")
            continue

        response = result["messages"][-1].content if result["messages"] else ""
        print(f"🤖 Agent: {response}")

        conversation_history = _trim_history(result["messages"], cfg.agent.history_window)


if __name__ == "__main__":
    main()
