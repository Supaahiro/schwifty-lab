import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from langchain.tools import BaseTool, tool


class AgentMemory(BaseModel):
    user_info: dict[str, Any] = Field(
        description="Informations about the user.", default_factory=dict
    )


def save_agent_memory(memory: AgentMemory, file_path: str) -> None:
    """
    Save the AgentMemory object to a JSON file.

    Args:
      memory (AgentMemory): The AgentMemory object to save.
      file_path (str): Path to the JSON file where the memory is stored.

    """

    path = Path(file_path)
    path.write_text(memory.model_dump_json(indent=4), encoding="utf-8")


def load_agent_memory(file_path: str) -> AgentMemory:
    """
    Read the AgentMemory object from a JSON file. If the file does not exist, return an empty memory.

    Args:
      file_path (str): Path to the JSON file where the memory is stored.

    Returns:
        AgentMemory: The loaded agent memory object.
    """

    path = Path(file_path)

    if not path.exists():
        return AgentMemory()

    data = json.loads(path.read_text(encoding="utf-8"))
    return AgentMemory(**data)


def get_memory_tools(file_path: str) -> list[BaseTool]:
    """
    It returns the tools to get and update the bot memory stored in a JSON file.

    Args:
        file_path (str): Path to the JSON file where the memory is stored.
    Returns:
        list[BaseTool]: A list containing the get_memory and update_memory tools.
    """

    @tool
    def get_memory_tool() -> AgentMemory | str:
        """
        Retrieves the bot's memory from a JSON file.

        Returns:
            AgentMemory: The loaded agent memory object if successful.
            str: An error message if reading the memory fails.

        Raises:
            Exception: If there is an issue loading the memory from the file.       
            """
        try:
            return load_agent_memory(file_path)
        except Exception as e:
            return f"Error reading memory: {str(e)}"

    @tool
    def update_memory_tool(updated_memory: Any) -> str:
        """
        Update the existing memory by merging new values.

        Accepts:
         - AgentMemory instance
         - dict (either {"user_info": {...}} or top-level keys to merge into user_info)
         - JSON string representing one of the above

        Behavior:
         - merges provided user_info into existing.user_info
         - treats any top-level unknown keys as user_info entries
        """
        try:
            memory = load_agent_memory(file_path)

            # TODO - This stuff needs to be rewritten, but it works for now, so I'm keeping it.

            # Normalize the incoming memory into a dict
            if isinstance(updated_memory, AgentMemory):
                incoming = updated_memory.model_dump()
            elif isinstance(updated_memory, str):
                try:
                    incoming = json.loads(updated_memory)
                except json.JSONDecodeError:
                    return "Error: provided string is not valid JSON."
            elif isinstance(updated_memory, dict):
                incoming = updated_memory
            else:
                # Try to coerce (fallback)
                try:
                    incoming = json.loads(json.dumps(updated_memory))
                except Exception:
                    return f"Unsupported memory input type: {type(updated_memory)}"

            # If user_info provided and is dict -> merge
            if "user_info" in incoming and isinstance(incoming["user_info"], dict):
                memory.user_info.update(incoming["user_info"])

            # Merge any other top-level keys into user_info (useful if agent sends {"favorite_color":"blue"})
            extra_top_level = {
                k: v for k, v in incoming.items() if k != "user_info"
            }
            if extra_top_level:
                memory.user_info.update(extra_top_level)

            # Persist merged memory
            save_agent_memory(memory, file_path)
            return "Memory updated successfully."
        except Exception as e:
            return f"Error updating memory: {str(e)}"

    return [get_memory_tool, update_memory_tool]
