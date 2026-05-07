from utils import client ,types, AgentState
import json
from tools import (
    check_ats_compatibility,
    search_job_market,
    find_youtube_resources,
    tools
)


def clean_llm_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()

def extract_node(state :AgentState):
    prompt = f"""
    You are an information extraction system.

Extract structured data from the following resume and job description.

Return ONLY valid JSON (no explanation, no markdown, no code blocks).
Do not wrap the response in backticks.

Schema:
{{
  "resume": {{
    "skills": [],
    "education": [],
    "experience": [],
    "projects": [],
    "achievements": [],
    "certifications": []
  }},
  "job_description": {{
    "required_skills": [],
    "preferred_skills": [],
    "qualifications": [],
    "responsibilities": []
  }}
}}

Resume:
{state["resume_text"]}

Job Description:
{state["jd_text"]}
"""

    
    response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=prompt
)
    
    try:
        cleaned = clean_llm_json(response.text)
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        parsed = {"error": "invalid json from llm", "raw": response.text}

    return {
        **state,
        "resume_data": parsed.get("resume", {}),
        "jd_data": parsed.get("job_description", {})
    }



def analyze_node(state : AgentState):
    tool_results = state.get("tool_results", {})
    ats = tool_results.get("ats", {})
    job_market = tool_results.get("job_market", [])
    prompt = f"""
   You are an experienced recruiter.

   Compare the resume data with the job description data and provide detailed, practical feedback.

   Focus on:

   1. Identify missing skills, qualifications, or experience in the resume compared to the job description.
   - Suggest practical ways to include them (projects, coursework, phrasing, etc.)

   2. Highlight strong points in the resume that align well with the job description.

   3. Provide specific, actionable suggestions to improve the resume.
   - Avoid generic advice like "improve skills"

   4. Suggest how to rewrite or better present existing experience, projects to match the job description.
   - Give concrete examples where possible

   Be specific and actionable. Avoid generic advice.

   Structure your response in a clear and readable way using sections,
   but you are free to decide the section names based on the context.

   If resume_data or jd_data appear empty or malformed, 
   say so clearly rather than hallucinating content.

   Resume Data:
   {json.dumps(state["resume_data"], indent=2)}

   Job Description Data:
   {json.dumps(state["jd_data"], indent=2)}

    """
    response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=prompt
)

    return {
        **state,
        "analysis": response.text
    }

def compress_history(history: list, max_turns: int = 6) -> list:
    if len(history) <= max_turns * 2:
        return history
    return history[:2] + history[-(max_turns * 2 - 2):]

def chat_node(state : AgentState) -> AgentState:
    compressed=compress_history(state["chat_history"])

    history_text=""
    for msg in state["chat_history"]:
        role="User" if msg["role"] == "user" else "Assistant"
        history_text += f"{role} : {msg['content']}\n"

    prompt=f"""
    You are a professional resume coach and career advisor.
    
    You have already analyzed the user's resume against a job description.
    Use this context to answer their questions specifically and accurately.
    
    === RESUME DATA ===
    {json.dumps(state["resume_data"], indent=2)}
    
    === JOB DESCRIPTION DATA ===
    {json.dumps(state["jd_data"], indent=2)}
    
    === INITIAL ANALYSIS ===
    {state["analysis"]}
    
    === CONVERSATION SO FAR ===
    {history_text}
    
    === USER'S CURRENT MESSAGE ===
    {state["user_message"]}
    
    Instructions:
    - Answer specifically based on THEIR resume and THEIR job description
    - Never give generic advice — always reference actual content
    - If they ask to rewrite something, give a concrete rewritten version
    - If they ask about a skill they don't have, suggest realistic ways 
      to demonstrate it based on what they do have
    - Be encouraging but honest
    """
    response=client.models.generate_content(
    model="gemini-2.5-flash",
    contents=prompt
)

    updated_history=state["chat_history"]+[
        {"role":"user","content":state["user_message"]},
        {"role":"assistant","content":response.text}
    ]

    return {
        **state,
        "chat_history":updated_history
    }

def route_chat(state: AgentState) -> str:
    user_msg = state["user_message"].lower()
    end_triggers = ["bye", "exit", "quit", "thanks", "done"]
    
    if any(trigger in user_msg for trigger in end_triggers):
        return "end"
    return "chat"

from tools import check_ats_compatibility


def agent_node(state:AgentState) -> AgentState:
    prompt = f"""
    You are a resume analysis agent.
    
    You have access to tools to analyze a resume against a job description.
    
    Resume Data: {json.dumps(state["resume_data"], indent=2)}
    JD Data: {json.dumps(state["jd_data"], indent=2)}
    
    Use your tools to gather all necessary information
    for a comprehensive resume analysis.
    Identify missing skills and gather market data for each.
    """
    response=client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(tools=[tools])
    )

    tool_calls=[]
    for part in response.candidates[0].content.parts:
        if hasattr(part,"function_call"):
            tool_calls.append({
                "tool":part.function_call.name,
                "args":dict(part.function_call.args)
            })
    return {**state, "tool_calls":tool_calls}


def tool_node(state: AgentState) -> AgentState:
    """
    Executes all tools that agent_node decided to call.
    """
    tool_results = {
        "ats": {},
        "job_market": [],
        "youtube_resources": []
    }

    for call in state.get("tool_calls", []):
        tool = call.get("tool")
        skill = call.get("skill", "")

        if tool == "check_ats":
            tool_results["ats"] = check_ats_compatibility(
                state["resume_text"],
                state["jd_text"]
            )

        elif tool == "search_job_market":
            result = search_job_market(skill)
            tool_results["job_market"].append(result)

        elif tool == "find_youtube_resources":
            result = find_youtube_resources(skill)
            tool_results["youtube_resources"].append(result)

    return {
        **state,
        "tool_results": tool_results
    }