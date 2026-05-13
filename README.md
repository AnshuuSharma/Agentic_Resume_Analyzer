ResumeIQ — Agentic Resume Analyzer
An AI-powered resume analyzer that compares your resume against a job description and gives you actionable feedback. It checks ATS compatibility, searches live job market data, finds free YouTube learning resources, and lets you chat with an AI coach about your resume.

What It Does :

1) You upload your resume (PDF or DOCX) and paste a job description
2) The AI extracts skills, experience, and education from both
3) It checks how well your resume will pass ATS (Applicant Tracking Systems)
4) It searches live job postings to show how in-demand your missing skills are
5) It finds free YouTube tutorials for skills you need to learn
6) It generates a detailed analysis with specific, actionable suggestions
7) You can chat with the AI to ask follow-up questions about your resume

TECH STACK
Backend

1) Python + Flask
2) LangGraph — stateful agent graph with 5 nodes
3) Groq API — llama-3.1-8b-instant for extraction and chat, llama-3.3-70b-versatile for analysis
4) Adzuna API — live job market data
5) YouTube Data API v3 — free learning resources
6) PyMuPDF + python-docx — resume file parsing

Frontend

1) Plain HTML, CSS, JavaScript
2) Tailwind CSS (via CDN)

Setup

1. Clone the repo
```
git clone https://github.com/yourusername/resume-analyzer-agent
cd resume-analyzer-agent
```

2. Create virtual environment
```
python -m venv venv
venv\Scripts\activate       # Windows
source venv/bin/activate    # Mac/Linux
```


3. Install dependencies
```
cd backend
pip install -r requirements.txt
```

5. Create .env file in backend folder
```
GROQ_API_KEY=your_groq_api_key
ADZUNA_APP_ID=your_adzuna_app_id
ADZUNA_APP_KEY=your_adzuna_app_key
YOUTUBE_API_KEY=your_youtube_api_key
```

6. Run the backend
```
python main.py
```

8. Open the frontend
Open frontend/index.html directly in your browser with live server.
No build step needed.

API Endpoints
```
POST /analyze
  Body: form-data
    resume: file (PDF or DOCX)
    jd_text: string
  Returns: { analysis: string, session_id: string }

POST /chat
  Body: JSON
    message: string
    session_id: string
  Returns: { response: string }
```

Limitations

Free tier APIs have daily token limits — heavy usage may hit rate limits
PyMuPDF struggles with two-column resume layouts
Scanned or image-based PDFs cannot be parsed (no text layer)
Sessions are stored in memory and reset when the server restarts
