from dotenv import load_dotenv
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage
from langgraph.graph.state import CompiledStateGraph

from agent import build_agent, print_graph
from core.config import Config
from core.vectordb import build_embeddings, vdb_builder
from providers import PROVIDERS
from tools import load_all_tools


def build_app(cfg: Config) -> CompiledStateGraph:
    """Builds the chat model, tools, and compiled LangGraph agent from a loaded Config."""

    provider_config = cfg.openai if cfg.provider == "openai" else cfg.llamacpp
    build_chat_model = PROVIDERS.get(cfg.provider)
    if build_chat_model is None or provider_config is None:
        raise ValueError(f"Unknown provider '{cfg.provider}'. Check config.json.")
    llm = build_chat_model(provider_config)

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

    return build_agent(llm, all_tools)


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

    load_dotenv()  # Load secrets from .env (OPENAI_API_KEY, optional LangSmith vars)
    cfg = Config.load_from_file("config.json")
    app = build_app(cfg)

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
