import os
import httpx

def check_ats_compatibility(resume_text:str, jd_text:str)-> dict:

    """
    checks if resume will pass ATS filters.
    Analyzes keyword match, formatting issues, and section headings.
    """
    resume_lower=resume_text.lower()
    jd_lower=jd_text.lower()

    import re 
    jd_words=set(re.findall(r'b[a-zA-Z]{4,}\b',jd_lower))
    resume_Words=set(re.findall(r'b[a-zA-Z]{4,}\b',resume_lower))

    matched_keywords=jd_words & resume_Words
    missing_keywords=jd_words-resume_Words

    match_percentage=round(
        len(matched_keywords)/len(jd_words)*100
        if jd_words else 0,2
    )

    formatting_issues=[]

    if "table" in resume_lower or "coulumns" in resume_lower:
        formatting_issues.append(
            "Possible table or column layout detected — ATS may misread this"
        )
    if not any (heading in resume_lower for heading in ["experience", "education", "skills","projects"]):
        formatting_issues.append(
            "Missing standard section headings — ATS may not parse sections correctly"
        )
    if resume_text.count("|") > 5:
        formatting_issues.append(
            "Too many pipe characters — suggests column layout which confuses ATS"
        )

    if len(resume_text) < 300:
        formatting_issues.append(
            "Resume seems too short — may not have enough content for ATS"
        )
    top_missing=sorted(list(missing_keywords))[:15]
    return{
        "match_percentage": match_percentage,
        "matched_keywords": sorted(list(matched_keywords))[:20],
        "missing_keywords": top_missing,
        "formatting_issues": formatting_issues,
        "ats_passed": match_percentage >= 60 and len(formatting_issues) == 0
    }

def search_job_market(skill:str,  country:str = "in")-> dict:
    """
    Searches live job postings for a specific skill using Adzuna API.
    Use this to find how in-demand a skill is in the current job market.
    """
    try:
        url=(
            f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
            f"?app_id={os.gentenv('ADZUNA_APP_ID')}"
            f"&app_key={os.getenv('ADZUNA_APP_KEY')}"
            f"&what={skill}"
            f"&results_per_page=5"
            f"&content-type=application/json"
        )
    
    
        response=httpx.get(url, timeout=10)
        data=response.json()

        total_jobs=data.get("count",0)
        results=data.get("results",[])

        top_companies = list(set([
            job.get("company", {}).get("display_name", "Unknown")
            for job in results
            if job.get("company", {}).get("display_name")
        ]))[:5]

        avg_salary=None
        salaries=[
            job.get("salary_min") for job in results
                if job.get("salary_min")
            ]
        if salaries:
                avg_salary = round(sum(salaries) / len(salaries))
    
        return {
            "skill": skill,
            "total_jobs": total_jobs,
            "demand": (
                "Very High" if total_jobs > 10000 else
                "High" if total_jobs > 5000 else
                "Medium" if total_jobs > 1000 else
                "Low"
            ),
            "top_companies_hiring": top_companies,
            "average_salary": avg_salary,
            "sample_job_titles": [
                job.get("title", "") for job in results[:3]
            ]
        }
    except Exception as e:
        return {
            "skill": skill,
            "error": f"Could not fetch job market data: {str(e)}"
        }

    