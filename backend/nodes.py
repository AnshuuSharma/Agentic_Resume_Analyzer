from utils import groq_client , AgentState, generate_with_retry, generate_fast
import json
from tools import (
    check_ats_compatibility,
    search_job_market,
    find_youtube_resources,
)


def clean_llm_json(text: str) -> str:
    import re
    text = text.strip()
    
    # Remove markdown code blocks
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()
    
    # Detect if it is an object or array and extract accordingly
    obj_start = text.find("{")
    arr_start = text.find("[")
    
    if obj_start != -1 and (arr_start == -1 or obj_start < arr_start):
        # It is a JSON object
        end = text.rfind("}")
        if end != -1:
            text = text[obj_start:end+1]
    elif arr_start != -1:
        # It is a JSON array
        end = text.rfind("]")
        if end != -1:
            text = text[arr_start:end+1]
    
    # Remove trailing commas before ] or }
    text = re.sub(r',\s*([}\]])', r'\1', text)
    
    # Fix unescaped newlines inside strings
    text = re.sub(r'(?<!\\)\n(?=[^"]*"(?:[^"]*"[^"]*")*[^"]*$)', ' ', text)
    
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

    
    result = generate_fast(prompt)
    print(f"RAW EXTRACTION RESULT: {result[:200]}")
    
    try:
        cleaned = clean_llm_json(result)
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        print(f"JSON PARSE FAILED: {result[:300]}")
        parsed = {"error": "invalid json from llm", "raw": result}

    print(f"PARSED RESUME KEYS: {list(parsed.get('resume', {}).keys())}")

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

    Compare the resume data with the job description and provide 
    concise, practical feedback. Skip lengthy introductions.

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

    Structure your response with these sections in order:

    1. ATS Score — state the exact match percentage and whether it passed.
       List the top missing keywords the candidate should add.

    2. Strong Points — what aligns well with the JD.

    3. Skill Gaps — for each missing skill mention:
       - How many jobs demand it (from job market data above)
       - One practical way to demonstrate it

    4. Learning Resources — for each missing skill list the 
       YouTube video title and full URL from the data above.
       Only include videos actually provided above.

    5. Resume Rewrites — rewrite 2-3 existing bullet points 
       to better match the JD using only what is in the resume.

    CRITICAL RULES:
    - Every rewrite must be based ONLY on what is explicitly 
      stated in the resume data — never invent new content
    - Never add technologies not mentioned in the original resume
    - If suggesting something new phrase it as "Consider adding 
      X if you actually did this"
    - When evaluating skills check BOTH skills list AND project 
      descriptions — if a skill appears in a project it counts
    - Never say a skill has no evidence if it appears in projects
    - Do not use markdown tables
    - No lengthy introductions
    - For missing skills suggest learning them as new skills
      not rewriting existing experience to include them
    - Phrase new suggestions as "To add this skill, consider 
      building a small project with X"
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

def chat_node(state: AgentState) -> AgentState:
    compressed = compress_history(state["chat_history"])

    history_text = ""
    for msg in compressed:
        role = "User" if msg["role"] == "user" else "Assistant"
        history_text += f"{role}: {msg['content']}\n"

    resume_skills = state["resume_data"].get("skills", [])
    resume_experience = state["resume_data"].get("experience", [])
    resume_projects = state["resume_data"].get("projects", [])
    required_skills = state["jd_data"].get("required_skills", [])
    preferred_skills = state["jd_data"].get("preferred_skills", [])

    missing_skills = [
        s for s in required_skills + preferred_skills
        if s.lower() not in [r.lower() for r in resume_skills]
    ]

    prompt = f"""
    You are a professional resume coach. Be concise and direct.
    Maximum 3-4 short paragraphs. No markdown tables.

    CANDIDATE'S ACTUAL SKILLS: {resume_skills}
    CANDIDATE'S EXPERIENCE: {resume_experience}
    CANDIDATE'S PROJECTS: {resume_projects}
    JOB REQUIRES: {required_skills}
    JOB PREFERS: {preferred_skills}
    GENUINELY MISSING SKILLS: {missing_skills}

    CRITICAL RULES:
    - Only reference skills actually listed above
    - Never suggest learning a skill already in CANDIDATE'S ACTUAL SKILLS
    - Never fabricate experience not mentioned above
    - If a skill appears in JOB REQUIRES it IS a requirement
    - Base every answer strictly on the data above
    - Do not use markdown tables
    - Every rewrite must be based ONLY on what is explicitly 
    stated in the resume data provided
    - Never add technologies, responsibilities, or achievements
    that are not mentioned in the original resume
    - If you want to suggest adding something new, phrase it as
    "Consider adding X if you actually did this" — never present
    fabricated content as a rewrite of existing experience
    - Rewriting means rephrasing what exists — not inventing new content

    CONVERSATION SO FAR:
    {history_text}

    USER MESSAGE: {state["user_message"]}
    """

    result = generate_with_retry(prompt)

    updated_history = state["chat_history"] + [
        {"role": "user", "content": state["user_message"]},
        {"role": "assistant", "content": result}
    ]

    return {**state, "chat_history": updated_history}

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
    - Maximum 3 missing skills — no more than 3
    - Return empty array [] if no skills are missing
    - Each skill must be a simple short name like "Docker" not 
     "RAG (Retrieval-Augmented Generation)"
    """
    result = generate_fast(prompt)

    try:
        cleaned = clean_llm_json(result)
        tool_calls = json.loads(cleaned)
        if not isinstance(tool_calls, list):
            tool_calls = []
        tool_calls = tool_calls[:6]
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

        # if tool == "check_ats_compatibility":
        #     tool_results["ats"] = check_ats_compatibility(
        #         args.get("resume_text", state["resume_text"]),
        #         args.get("jd_text", state["jd_text"])
        #     )

        if tool == "search_job_market":
            result = search_job_market(args.get("skill", ""))
            tool_results["job_market"].append(result)

        elif tool == "find_youtube_resources":
            result = find_youtube_resources(args.get("skill", ""))
            tool_results["youtube_resources"].append(result)

    return {
        **state,
        "tool_results": tool_results
    }
