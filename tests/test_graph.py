from unittest.mock import MagicMock, patch
from ai.graph import load_memory, agent, execute_tools, save_memory, route_after_agent, route_after_tools, GraphState


def _base_state(**overrides) -> GraphState:
    state: GraphState = {
        "user_id": "user123",
        "user_message": "track hades",
        "messages": [{"role": "user", "content": "track hades"}],
        "tool_iteration": 0,
        "final_reply": "",
        "pending_tool_calls": [],
    }
    state.update(overrides)
    return state


# --- load_memory ---

def test_load_memory_injects_system_prompt(mocker):
    mocker.patch("ai.graph.get_chat_context", return_value={"summary": None, "messages": []})
    result = load_memory(_base_state())
    assert result["messages"][0]["role"] == "system"
    assert "DropHunter" in result["messages"][0]["content"]


def test_load_memory_injects_summary_into_system(mocker):
    mocker.patch("ai.graph.get_chat_context", return_value={
        "summary": "User tracks Hades.",
        "messages": [],
    })
    result = load_memory(_base_state())
    assert "User tracks Hades." in result["messages"][0]["content"]


def test_load_memory_prepends_history_messages(mocker):
    mocker.patch("ai.graph.get_chat_context", return_value={
        "summary": None,
        "messages": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}],
    })
    result = load_memory(_base_state())
    # system + 2 history + 1 current = 4
    assert len(result["messages"]) == 4


# --- agent ---

def test_agent_returns_final_reply_on_text(mocker):
    mock_provider = MagicMock()
    mock_provider.chat_with_tools.return_value = {"text": "Here is the price."}
    mocker.patch("ai.graph.get_provider", return_value=mock_provider)
    result = agent(_base_state())
    assert result["final_reply"] == "Here is the price."
    assert result["pending_tool_calls"] == []


def test_agent_returns_tool_calls(mocker):
    mock_provider = MagicMock()
    mock_provider.chat_with_tools.return_value = {
        "tool_calls": [{"name": "list_games", "arguments": {}}]
    }
    mocker.patch("ai.graph.get_provider", return_value=mock_provider)
    result = agent(_base_state())
    assert result["pending_tool_calls"] == [{"name": "list_games", "arguments": {}}]
    assert result["final_reply"] == ""


# --- execute_tools ---

def test_execute_tools_dispatches_and_appends_results(mocker):
    mocker.patch("ai.graph.dispatch", return_value="Game list: Hades")
    state = _base_state(pending_tool_calls=[{"name": "list_games", "arguments": {}}])
    result = execute_tools(state)
    assert result["tool_iteration"] == 1
    assert any("Game list: Hades" in m["content"] for m in result["messages"])


def test_execute_tools_stops_at_max_iterations(mocker):
    state = _base_state(tool_iteration=7, pending_tool_calls=[{"name": "list_games", "arguments": {}}])
    result = execute_tools(state)
    assert "wasn't able to complete" in result["final_reply"]


def test_execute_tools_handles_tool_error(mocker):
    mocker.patch("ai.graph.dispatch", side_effect=Exception("DB error"))
    state = _base_state(pending_tool_calls=[{"name": "list_games", "arguments": {}}])
    result = execute_tools(state)
    assert any("Error in list_games" in m["content"] for m in result["messages"])


# --- save_memory ---

def test_save_memory_calls_save_turn(mocker):
    mock_save = mocker.patch("ai.graph.save_turn")
    mocker.patch("ai.graph.GeminiProvider")
    mocker.patch("ai.graph.summarize_if_needed")
    state = _base_state(final_reply="Now tracking Hades.")
    save_memory(state)
    mock_save.assert_called_once_with("user123", "track hades", "Now tracking Hades.")


def test_save_memory_does_not_raise_on_failure(mocker):
    mocker.patch("ai.graph.save_turn", side_effect=Exception("supabase down"))
    state = _base_state(final_reply="ok")
    save_memory(state)  # should not raise


# --- routing ---

def test_route_after_agent_goes_to_tools_when_pending(mocker):
    state = _base_state(pending_tool_calls=[{"name": "list_games", "arguments": {}}], final_reply="")
    assert route_after_agent(state) == "execute_tools"


def test_route_after_agent_goes_to_save_when_reply(mocker):
    state = _base_state(final_reply="Here you go.", pending_tool_calls=[])
    assert route_after_agent(state) == "save_memory"


def test_route_after_tools_goes_to_agent_when_no_reply(mocker):
    state = _base_state(final_reply="", pending_tool_calls=[])
    assert route_after_tools(state) == "agent"


def test_route_after_tools_goes_to_save_when_reply(mocker):
    state = _base_state(final_reply="Done.", pending_tool_calls=[])
    assert route_after_tools(state) == "save_memory"
