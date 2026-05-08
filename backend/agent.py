from langgraph.graph import StateGraph, START,END
from utils import  AgentState
from langgraph.checkpoint.memory import MemorySaver
from nodes import extract_node,analyze_node,agent_node,tool_node,chat_node,route_chat

memory=MemorySaver()
graph=StateGraph(AgentState)

graph.add_node("extract", extract_node)
graph.add_node("agent", agent_node)      
graph.add_node("tools", tool_node)       
graph.add_node("analyze", analyze_node)
graph.add_node("chat", chat_node)

graph.set_entry_point("extract")
graph.add_edge("extract", "agent")        
graph.add_edge("agent", "tools")          
graph.add_edge("tools", "analyze")      
graph.add_edge("analyze", "chat")

graph.add_conditional_edges(
    "chat",
    route_chat,
    {
        "chat": "chat",
        "end": END
    }
)


app=graph.compile(checkpointer=memory, interrupt_before=["chat"])


