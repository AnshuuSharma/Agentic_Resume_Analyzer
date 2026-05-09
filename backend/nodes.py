from utils import groq_client , AgentState, generate_with_retry
import json
from tools import (
    check_ats_compatibility,
    search_job_market,
    find_youtube_resources,
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

    
    result = generate_with_retry(prompt)
    
    try:
        cleaned = clean_llm_json(result)
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        parsed = {"error": "invalid json from llm", "raw": result}

    return {
        **state,
        "resume_data": parsed.get("resume", {}),
        "jd_data": parsed.get("job_description", {})
    }



def analyze_node(state : AgentState):
    tool_results = state.get("tool_results", {})
    print(f"TOOL RESULTS: {json.dumps(tool_results, indent=2)}")
    ats = tool_results.get("ats", {})
    job_market = tool_results.get("job_market", [])
    youtube = tool_results.get("youtube_resources", [])
    prompt = f"""
    You are an experienced recruiter and career coach talking directly 
    to a job candidate. Use "you" and "your" — never refer to them 
    in third person.
    
    A candidate has submitted their resume for a specific job.
    You have been provided with structured resume data, job description 
    data, ATS compatibility results, live job market data, and learning 
    resources.

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

    === ATS COMPATIBILITY RESULTS ===
    Your resume currently matches {ats.get("match_percentage", "N/A")}% 
    of the job description keywords.
    ATS Passed: {ats.get("ats_passed", "N/A")}
    Keywords you are missing: {ats.get("missing_keywords", [])}
    Formatting Issues: {ats.get("formatting_issues", [])}
    Matched Keywords: {ats.get("matched_keywords", [])}
    
    === LIVE JOB MARKET DATA FOR MISSING SKILLS ===
    {json.dumps(job_market, indent=2)}

    === LEARNING RESOURCES FOR MISSING SKILLS ===
    {json.dumps(youtube, indent=2)}

    Based on all the data above, provide a detailed and actionable 
    resume analysis. Structure your response however makes most sense 
    for this specific resume and job description.
    Use all the data provided above including ATS results, job market
    data and learning resources in your analysis.
    Include the full YouTube URLs and video title from the learning resources above

    """
    result = generate_with_retry(prompt)

    return {
        **state,
        "analysis": result
    }

def compress_history(history: list, max_turns: int = 6) -> list:
    if len(history) <= max_turns * 2:
        return history
    return history[:2] + history[-(max_turns * 2 - 2):]

def chat_node(state : AgentState) -> AgentState:
    compressed=compress_history(state["chat_history"])

    history_text=""
    for msg in compressed:
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
    result = generate_with_retry(prompt)

    updated_history=state["chat_history"]+[
        {"role":"user","content":state["user_message"]},
        {"role":"assistant","content":result}
    ]

    return {
        **state,
        "chat_history":updated_history
    }

def route_chat(state: AgentState) -> str:
    user_msg = state.get("user_message", "")
    
    if not isinstance(user_msg, str):
        return "end"
    
    user_msg = user_msg.lower()
    end_triggers = ["bye", "exit", "quit", "thanks", "done"]
    
    if any(trigger in user_msg for trigger in end_triggers):
        return "end"
    return "chat"


def agent_node(state:AgentState) -> AgentState:
    tools = [
        
        {
            "type": "function",
            "function": {
                "name": "search_job_market",
                "description": "Searches live job postings for a skill. Use to find how in-demand a missing skill is.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "skill": {"type": "string"}
                    },
                    "required": ["skill"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "find_youtube_resources",
                "description": "Finds YouTube tutorials for a skill. Use when user needs to learn a missing skill.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "skill": {"type": "string"}
                    },
                    "required": ["skill"]
                }
            }
        }
    ]
    prompt = f"""
    You are a resume analysis agent.
    
    You have access to tools to analyze a resume against a job description.
    
    Resume skills: {state["resume_data"].get("skills", [])}
    Required skills: {state["jd_data"].get("required_skills", [])}
    Preferred skills: {state["jd_data"].get("preferred_skills", [])}
    
    Use your tools to gather all necessary information
    for a comprehensive resume analysis.

    Return ONLY a valid JSON array of tool calls. No explanation. No markdown.
    
    Available tools:
    - search_job_market: searches live job postings for a skill
    - find_youtube_resources: finds YouTube tutorials for a skill
    
    Example output:
    [
        {{"tool": "search_job_market", "args": {{"skill": "Docker"}}}},
        {{"tool": "find_youtube_resources", "args": {{"skill": "Docker"}}}},
        {{"tool": "search_job_market", "args": {{"skill": "Kubernetes"}}}},
        {{"tool": "find_youtube_resources", "args": {{"skill": "Kubernetes"}}}}
    ]
    
    Rules:
    - Only include tools for skills that are genuinely missing from the resume
    - Maximum 3 missing skills
    - Return empty array [] if no skills are missing
    """
    result = generate_with_retry(prompt)

    try:
        cleaned = clean_llm_json(result)
        tool_calls = json.loads(cleaned)
        if not isinstance(tool_calls, list):
            tool_calls = []
    except json.JSONDecodeError:
        print(f"Failed to parse tool calls JSON: {result}")
        tool_calls = []

    print(f"TOOL CALLS DECIDED: {tool_calls}")
    return {**state, "tool_calls": tool_calls}


def tool_node(state: AgentState) -> AgentState:
    tool_results = {
        "ats": {},
        "job_market": [],
        "youtube_resources": []
    }

    tool_results["ats"] = check_ats_compatibility(
        state["resume_data"],
        state["jd_data"]
    )

    for call in state.get("tool_calls", []):
        tool = call.get("tool")
        args = call.get("args", {})

        if tool == "check_ats_compatibility":
            tool_results["ats"] = check_ats_compatibility(
                args.get("resume_text", state["resume_text"]),
                args.get("jd_text", state["jd_text"])
            )

        elif tool == "search_job_market":
            result = search_job_market(args.get("skill", ""))
            tool_results["job_market"].append(result)

        elif tool == "find_youtube_resources":
            result = find_youtube_resources(args.get("skill", ""))
            tool_results["youtube_resources"].append(result)

    return {
        **state,
        "tool_results": tool_results
    }