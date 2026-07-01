from typing import Annotated, Final, Literal, Sequence, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import BaseTool
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from core.prompts import SYSTEM_PROMPT


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]


AGENT_NODE: Final = "agent"
TOOLS_NODE: Final = "tools"


def build_agent(llm: BaseChatModel, tools: list[BaseTool]) -> CompiledStateGraph:
    """
    Compiles a LangGraph ReAct agent from a chat model and a list of tools.

    The agent loop:
      1. Agent node calls the LLM with the current message history.
      2. If the LLM requests tool calls, the tools node executes them.
      3. Tool results are fed back to the agent node.
      4. The loop continues until the LLM returns a plain text response.

    Args:
      llm (BaseChatModel): A LangChain-compatible chat model with tool-calling support.
      tools (list[BaseTool]): The tools available to the agent.

    Returns:
      CompiledStateGraph: The compiled, executable LangGraph application.
    """

    generation_prompt = ChatPromptTemplate.from_messages(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )

    bound_llm = llm.bind_tools(tools=tools)
    generate_chain = generation_prompt | bound_llm

    def query_agent(state: AgentState) -> AgentState:
        print("🤖 Querying the agent")
        result = generate_chain.invoke({"messages": state["messages"]})
        tool_calls = result.tool_calls if isinstance(result, AIMessage) else []
        return {"messages": [AIMessage(content=result.content, tool_calls=tool_calls)]}

    def route_from_agent_to_tools(state: AgentState):
        result = state["messages"][-1]
        if isinstance(result, AIMessage) and len(result.tool_calls) > 0:
            for tool_call in result.tool_calls:
                print(f"\n🛠️ Agent decided to use tool: {tool_call['name']}")
            return True
        return False

    builder = StateGraph(state_schema=AgentState)
    builder.add_node(AGENT_NODE, query_agent)
    builder.add_node(TOOLS_NODE, ToolNode(tools))
    builder.add_conditional_edges(
        AGENT_NODE,
        route_from_agent_to_tools,
        {True: TOOLS_NODE, False: END},
    )
    builder.add_edge(TOOLS_NODE, AGENT_NODE)
    builder.set_entry_point(AGENT_NODE)

    return builder.compile()


def print_graph(app: CompiledStateGraph, output_format: Literal["ascii", "mermaid"]) -> None:
    """
    Prints a visual representation of the compiled agent graph.

    Args:
      app (CompiledStateGraph): The compiled agent graph.
      output_format (Literal["ascii", "mermaid"]): Output format.
    """

    graph = app.get_graph()

    if output_format == "ascii":
        graph.print_ascii()
    elif output_format == "mermaid":
        print(graph.draw_mermaid())
    else:
        raise ValueError("Unsupported graph type. Use 'ascii' or 'mermaid'.")
