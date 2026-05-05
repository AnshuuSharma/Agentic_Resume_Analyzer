from langgraph.graph import StateGraph, START,END
from utils import  AgentState
from langgraph.checkpoint.memory import MemorySaver
from nodes import extract_node,analyze_node,chat_node,route_chat

memory=MemorySaver()
graph=StateGraph(AgentState)

graph.add_node("extract",extract_node)
graph.add_node("analyze",analyze_node)
graph.add_node("chat",chat_node)

graph.set_entry_point("extract")
graph.add_edge("extract","analyze")
graph.add_edge("analyze","chat")

graph.add_conditional_edges(
    "chat",
    route_chat,
    {
        "chat": "chat",
        "end": END
    }
)


app=graph.compile(checkpointer=memory)

config={"configurable":{"thread_id":"user_session_123"}}

