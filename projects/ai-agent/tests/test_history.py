from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from main import _trim_history


def test_trim_history_keeps_everything_under_the_window():
    messages = [HumanMessage("hi"), AIMessage("hello")]

    result = _trim_history(messages, window=5)

    assert result == messages


def test_trim_history_cuts_cleanly_on_a_safe_boundary():
    messages = [
        HumanMessage("t1"),
        AIMessage("a1"),
        HumanMessage("t2"),
        AIMessage("a2"),
        HumanMessage("t3"),
    ]

    result = _trim_history(messages, window=2)

    assert result == messages[-2:]
    assert result[0] == AIMessage("a2")


def test_trim_history_walks_back_past_a_dangling_tool_message():
    tool_call = AIMessage(content="", tool_calls=[{"name": "foo", "args": {}, "id": "call_1"}])
    messages = [
        HumanMessage("t1"),
        tool_call,
        ToolMessage(content="result", tool_call_id="call_1"),
        AIMessage("final answer"),
        HumanMessage("t2"),
    ]

    # Naive cut at len(5) - 3 = index 2, which lands on the ToolMessage.
    result = _trim_history(messages, window=3)

    assert not isinstance(result[0], ToolMessage)
    assert result[0] is tool_call
    assert result == messages[1:]


def test_trim_history_stops_at_index_zero_if_no_safe_boundary_exists():
    messages = [
        ToolMessage(content="r1", tool_call_id="call_1"),
        ToolMessage(content="r2", tool_call_id="call_2"),
        ToolMessage(content="r3", tool_call_id="call_3"),
    ]

    result = _trim_history(messages, window=1)

    assert result == messages
