import logging
from typing import Literal, TypedDict

from langgraph.graph import END, StateGraph

from ai import get_provider
from ai.gemini_provider import GeminiProvider
from bot.functions import TOOLS, dispatch
from db.client import get_chat_context, save_turn, summarize_if_needed

logger = logging.getLogger("drophunter.graph")

MAX_TOOL_ITERATIONS = 7

_SYSTEM_PROMPT = (
    "You are DropHunter, a personal game deal assistant. "
    "When the user asks you to track, untrack, list games, check prices, see recent deals, "
    "check historical lows, or set target prices, use the available tools. "
    "You can call multiple tools in sequence if needed. "
    "For anything else, respond helpfully in plain text."
)


class GraphState(TypedDict):
    user_id: str
    user_message: str
    messages: list[dict]
    tool_iteration: int
    final_reply: str
    pending_tool_calls: list[dict]


def load_memory(state: GraphState) -> GraphState:
    context = get_chat_context(state["user_id"])

    system_content = _SYSTEM_PROMPT
    if context["summary"]:
        system_content += f"\n\nConversation history summary:\n{context['summary']}"

    history = [{"role": m["role"], "content": m["content"]} for m in context["messages"]]
    new_messages = (
        [{"role": "system", "content": system_content}]
        + history
        + [{"role": "user", "content": state["user_message"]}]
    )
    return {**state, "messages": new_messages}


def agent(state: GraphState) -> GraphState:
    provider = get_provider()
    # If tool results are already in messages, pass tools=[] to force a text response
    last_message = state["messages"][-1] if state["messages"] else {}
    has_tool_results = (
        last_message.get("role") == "user"
        and last_message.get("content", "").startswith("Tool results:")
    )
    tools = [] if has_tool_results else TOOLS
    result = provider.chat_with_tools(messages=state["messages"], tools=tools)

    if "tool_calls" in result:
        return {
            **state,
            "pending_tool_calls": result["tool_calls"],
            "final_reply": "",
        }
    return {
        **state,
        "final_reply": result.get("text", "I'm not sure how to help with that."),
        "pending_tool_calls": [],
    }


def execute_tools(state: GraphState) -> GraphState:
    if state["tool_iteration"] >= MAX_TOOL_ITERATIONS:
        return {
            **state,
            "final_reply": "I wasn't able to complete that — please try again.",
            "pending_tool_calls": [],
        }

    tool_responses = []
    for tc in state["pending_tool_calls"]:
        try:
            result = dispatch(tc["name"], tc.get("arguments") or {})
            tool_responses.append(result)
        except Exception as exc:
            tool_responses.append(f"Error in {tc['name']}: {exc}")

    new_messages = state["messages"] + [
        {"role": "user", "content": f"Tool results: {'; '.join(tool_responses)}"}
    ]
    return {
        **state,
        "messages": new_messages,
        "tool_iteration": state["tool_iteration"] + 1,
        "pending_tool_calls": [],
    }


def save_memory(state: GraphState) -> GraphState:
    try:
        save_turn(state["user_id"], state["user_message"], state["final_reply"])
        summarize_if_needed(state["user_id"], GeminiProvider())
    except Exception as exc:
        logger.warning("Failed to save memory for %s: %s", state["user_id"], exc)
    return state


def route_after_agent(state: GraphState) -> Literal["execute_tools", "save_memory"]:
    if state.get("pending_tool_calls"):
        return "execute_tools"
    return "save_memory"


def route_after_tools(state: GraphState) -> Literal["agent", "save_memory"]:
    if state.get("final_reply"):
        return "save_memory"
    return "agent"


def _build_graph():
    g = StateGraph(GraphState)
    g.add_node("load_memory", load_memory)
    g.add_node("agent", agent)
    g.add_node("execute_tools", execute_tools)
    g.add_node("save_memory", save_memory)

    g.set_entry_point("load_memory")
    g.add_edge("load_memory", "agent")
    g.add_conditional_edges("agent", route_after_agent)
    g.add_conditional_edges("execute_tools", route_after_tools)
    g.add_edge("save_memory", END)

    return g.compile()


_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = _build_graph()
    return _graph


def run_graph(user_id: str, user_message: str) -> str:
    initial_state: GraphState = {
        "user_id": user_id,
        "user_message": user_message,
        "messages": [{"role": "user", "content": user_message}],
        "tool_iteration": 0,
        "final_reply": "",
        "pending_tool_calls": [],
    }
    result = _get_graph().invoke(initial_state)
    return result["final_reply"]
