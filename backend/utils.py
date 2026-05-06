from google import genai
from google.genai import types
from dotenv import load_dotenv
import os

load_dotenv()

client=genai.Client(api_key=os.getenv('GEMINI_API_KEY'))



from typing import TypedDict,List


class AgentState(TypedDict):
    #input 
    resume_text:str
    jd_text:str

    #extraction 
    resume_data:dict
    jd_data:dict

    #tools
    job_market_result:dict
    ats_score:dict
    find_course_result:dict

    #analysis
    analysis:str

    #chat
    chat_history:List[dict]
    user_message:str
    
    #tools
    tool_calls: list        
    tool_results: dict   

import fitz 
from docx import Document
import io

def extract_text_from_file(file) -> str:
    filename = file.filename.lower()
    
    if filename.endswith(".pdf"):
        return extract_from_pdf(file)
    elif filename.endswith(".docx"):
        return extract_from_docx(file)
    else:
        raise ValueError("Unsupported file format. Please upload PDF or DOCX.")


def extract_from_pdf(file) -> str:
    try:
        pdf_bytes = file.read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        text = ""
        for page in doc:
            text += page.get_text()
        
        doc.close()
        
        if not text.strip():
            raise ValueError("PDF appears to be scanned or image-based. No text could be extracted.")
        
        return text.strip()
    
    except Exception as e:
        raise ValueError(f"Could not read PDF: {str(e)}")


def extract_from_docx(file) -> str:
    try:
        file_bytes = io.BytesIO(file.read())
        doc = Document(file_bytes)
        
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        
        if not text.strip():
            raise ValueError("DOCX file appears to be empty.")
        
        return text.strip()
    
    except Exception as e:
        raise ValueError(f"Could not read DOCX: {str(e)}")
    
# with open("resume.pdf", "rb") as f:
#     f.filename = "Anshu_Resume_SE.pdf"
#     print(extract_text_from_file(f))