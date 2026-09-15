import re
import json
import time
from utils import groq_client, AgentState, generate_with_retry, generate_fast
from tools import (
    check_ats_compatibility,
    search_job_market,
    find_youtube_resources,
)


FAST_MODEL = "openai/gpt-oss-20b"


def clean_llm_json(text: str) -> str:
    text = text.strip()

    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()

    obj_start = text.find("{")
    arr_start = text.find("[")

    if obj_start != -1 and (arr_start == -1 or obj_start < arr_start):
        end = text.rfind("}")
        if end != -1:
            text = text[obj_start:end + 1]
    elif arr_start != -1:
        end = text.rfind("]")
        if end != -1:
            text = text[arr_start:end + 1]

    text = re.sub(r',\s*([}\]])', r'\1', text)

    text = re.sub(r'(?<!\\)\n(?=[^"]*"(?:[^"]*"[^"]*")*[^"]*$)', ' ', text)

    return text.strip()



def get_missing_skills(resume_data: dict, target_skills: list) -> list:
    """
    Returns items from target_skills that aren't covered anywhere in the
    resume — checked against the skills list AND project/experience text,
    so a skill only mentioned inside a project still counts as covered.
    """
    resume_skills = resume_data.get("skills", [])
    resume_skills_lower = {s.lower().strip() for s in resume_skills if isinstance(s, str)}

    text_blobs = resume_data.get("projects", []) + resume_data.get("experience", [])
    combined_text = " ".join(str(b) for b in text_blobs).lower()

    missing = []
    for skill in target_skills:
        if not isinstance(skill, str):
            continue
        skill_lower = skill.lower().strip()
        if skill_lower in resume_skills_lower:
            continue
        if skill_lower and skill_lower in combined_text:
            continue
        missing.append(skill)

    return missing



def extract_node(state: AgentState):
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

    parsed = None
    last_raw = None

  
    for attempt in range(2):
        if attempt == 0:
            result = generate_with_retry(prompt)
        else:
            result = generate_fast(
                prompt + "\n\nYour previous response was not valid JSON. "
                         "Return ONLY valid JSON and nothing else."
            )

        last_raw = result
        print(f"RAW EXTRACTION RESULT (attempt {attempt + 1}): {result[:200]}")

        try:
            cleaned = clean_llm_json(result)
            parsed = json.loads(cleaned)
            break
        except json.JSONDecodeError:
            print(f"JSON PARSE FAILED (attempt {attempt + 1}): {result[:300]}")
            parsed = None

    if parsed is None:
   
        return {
            **state,
            "resume_data": {},
            "jd_data": {},
            "extraction_failed": True,
            "extraction_error": last_raw,
        }

    resume_data = parsed.get("resume", {}) or {}
    jd_data = parsed.get("job_description", {}) or {}

   
    for field in ["skills", "education", "experience", "projects", "achievements", "certifications"]:
        if not isinstance(resume_data.get(field), list):
            resume_data[field] = []

    for field in ["required_skills", "preferred_skills", "qualifications", "responsibilities"]:
        if not isinstance(jd_data.get(field), list):
            jd_data[field] = []

    print(f"PARSED RESUME KEYS: {list(resume_data.keys())}")

    return {
        **state,
        "resume_data": resume_data,
        "jd_data": jd_data,
        "extraction_failed": False,
    }


def _extract_section(text: str, heading: str, stop_headings: list) -> str:
    stop_pattern = "|".join(re.escape(h) for h in stop_headings)
    pattern = rf"{re.escape(heading)}.*?(?=(?:{stop_pattern})|$)"
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    return match.group(0) if match else ""


def _flag_possible_fabrications(rewrites_text: str, resume_data: dict) -> list:
    if not rewrites_text:
        return []

    vocab = {s.lower().strip() for s in resume_data.get("skills", []) if isinstance(s, str)}
    text_blobs = (
        resume_data.get("experience", [])
        + resume_data.get("projects", [])
        + resume_data.get("achievements", [])
    )
    combined_text = " ".join(str(b) for b in text_blobs).lower()


    candidates = set(re.findall(r"\b[A-Z][a-zA-Z0-9\.\+#]{1,}\b", rewrites_text))

    ignore = {"The", "This", "Consider", "Resume", "Rewrite", "Rewrites", "JD"}

    flagged = []
    for term in candidates:
        if term in ignore:
            continue
        term_lower = term.lower()
        if term_lower in vocab or term_lower in combined_text:
            continue
        flagged.append(term)

    return flagged


def analyze_node(state: AgentState):
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
    """
    result = generate_with_retry(prompt)

    rewrites_section = _extract_section(result, "5. Resume Rewrites", ["6.", "\Z"])
    flagged_terms = _flag_possible_fabrications(rewrites_section, state["resume_data"])

    if flagged_terms:
        print(f"POSSIBLE FABRICATION WARNING — terms not found in resume data: {flagged_terms}")
        result += (
            "\n\n[Auto-check: " + ", ".join(flagged_terms) + " appear in the "
            "rewrites above but weren't found in your original resume data. "
            "Double-check these weren't added by mistake.]"
        )

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

    missing_skills = get_missing_skills(state["resume_data"], required_skills + preferred_skills)

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



def _call_agent_with_tools(prompt: str, tools: list, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            return groq_client.chat.completions.create(
                model=FAST_MODEL,
                messages=[{"role": "user", "content": prompt}],
                tools=tools,
                tool_choice="auto",
            )
        except Exception as e:
            if "429" in str(e) or "rate" in str(e).lower():
                wait_time = 15 * (attempt + 1)
                print(f"Rate limit hit, waiting {wait_time}s...")
                time.sleep(wait_time)
            else:
                print(f"EXACT ERROR: {str(e)}")
                raise e
    raise Exception("Max retries exceeded. Please try again later.")


def agent_node(state: AgentState) -> AgentState:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_job_market",
                "description": "Searches live job postings for a skill. Use to find how in-demand a missing skill is.",
                "parameters": {
                    "type": "object",
                    "properties": {"skill": {"type": "string"}},
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
                    "properties": {"skill": {"type": "string"}},
                    "required": ["skill"]
                }
            }
        }
    ]

    resume_data = state["resume_data"]
    required_skills = state["jd_data"].get("required_skills", [])
    preferred_skills = state["jd_data"].get("preferred_skills", [])


    missing_skills = get_missing_skills(resume_data, required_skills + preferred_skills)[:3]

    if not missing_skills:
        print("NO MISSING SKILLS — SKIPPING TOOL CALLS")
        return {**state, "tool_calls": []}

    prompt = f"""
    You are a resume analysis agent. Use your tools to gather job market
    and learning resource data for the candidate's missing skills.

    Genuinely missing skills: {missing_skills}

    For each skill listed above, call both search_job_market and
    find_youtube_resources exactly once. Do not call tools for any
    skill not in that list.
    """

    response = _call_agent_with_tools(prompt, tools)

    raw_tool_calls = response.choices[0].message.tool_calls or []

    tool_calls = []
    seen = set() 

    for call in raw_tool_calls:
        try:
            args = json.loads(call.function.arguments)
        except (json.JSONDecodeError, AttributeError):
            print(f"COULD NOT PARSE TOOL CALL ARGS: {call}")
            continue

        skill = str(args.get("skill", "")).strip()
        if not skill:
            continue

        key = (call.function.name, skill.lower())
        if key in seen:
            continue
        seen.add(key)

        tool_calls.append({"tool": call.function.name, "args": {"skill": skill}})

    print(f"TOOL CALLS DECIDED: {tool_calls}")
    return {**state, "tool_calls": tool_calls}



def tool_node(state: AgentState) -> AgentState:
    tool_results = {
        "ats": {},
        "job_market": [],
        "youtube_resources": []
    }

    try:
        tool_results["ats"] = check_ats_compatibility(
            state["resume_data"],
            state["jd_data"]
        )
    except Exception as e:
        print(f"ATS CHECK FAILED: {e}")
        tool_results["ats"] = {}

    for call in state.get("tool_calls", []):
        tool = call.get("tool")
        skill = call.get("args", {}).get("skill", "")

        if tool == "search_job_market":
            try:
                result = search_job_market(skill)
                tool_results["job_market"].append(result)
            except Exception as e:
                print(f"JOB MARKET SEARCH FAILED for '{skill}': {e}")
                

        elif tool == "find_youtube_resources":
            try:
                result = find_youtube_resources(skill)
                tool_results["youtube_resources"].append(result)
            except Exception as e:
                print(f"YOUTUBE SEARCH FAILED for '{skill}': {e}")
                

    return {
        **state,
        "tool_results": tool_results
    }