import json

from tools.memory import AgentMemory, get_memory_tools, load_agent_memory


def test_update_memory_merges_user_info(tmp_path):
    memory_path = str(tmp_path / "memory.json")
    _, update_memory_tool = get_memory_tools(memory_path)

    result = update_memory_tool.invoke({"updated_memory": {"user_info": {"name": "Alice"}}})

    assert "successfully" in result.lower()
    assert load_agent_memory(memory_path).user_info == {"name": "Alice"}


def test_update_memory_promotes_unknown_top_level_keys(tmp_path):
    memory_path = str(tmp_path / "memory.json")
    _, update_memory_tool = get_memory_tools(memory_path)

    update_memory_tool.invoke({"updated_memory": {"favorite_color": "blue"}})

    assert load_agent_memory(memory_path).user_info == {"favorite_color": "blue"}


def test_update_memory_keeps_keys_that_are_substrings_of_user_info(tmp_path):
    """Regression test: `k not in ("user_info")` used to do a substring check
    against the string "user_info", silently dropping keys like "info" or "user"."""
    memory_path = str(tmp_path / "memory.json")
    _, update_memory_tool = get_memory_tools(memory_path)

    update_memory_tool.invoke({
        "updated_memory": {
            "user_info": {"name": "Alice"},
            "info": "should survive",
            "user": "should also survive",
        }
    })

    user_info = load_agent_memory(memory_path).user_info
    assert user_info["name"] == "Alice"
    assert user_info["info"] == "should survive"
    assert user_info["user"] == "should also survive"


def test_update_memory_accepts_json_string(tmp_path):
    memory_path = str(tmp_path / "memory.json")
    _, update_memory_tool = get_memory_tools(memory_path)

    payload = json.dumps({"user_info": {"role": "engineer"}})
    result = update_memory_tool.invoke({"updated_memory": payload})

    assert "successfully" in result.lower()
    assert load_agent_memory(memory_path).user_info == {"role": "engineer"}


def test_update_memory_rejects_invalid_json_string(tmp_path):
    memory_path = str(tmp_path / "memory.json")
    _, update_memory_tool = get_memory_tools(memory_path)

    result = update_memory_tool.invoke({"updated_memory": "not valid json"})

    assert "error" in result.lower()


def test_get_memory_returns_empty_memory_when_file_missing(tmp_path):
    memory_path = str(tmp_path / "missing.json")
    get_memory_tool, _ = get_memory_tools(memory_path)

    result = get_memory_tool.invoke({})

    assert isinstance(result, AgentMemory)
    assert result.user_info == {}
