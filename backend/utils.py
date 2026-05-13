from groq import Groq
from dotenv import load_dotenv
import os
import time

load_dotenv()


from typing import TypedDict,List


class AgentState(TypedDict):
    #input 
    resume_text:str
    jd_text:str

    #extraction 
    resume_data:dict
    jd_data:dict

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
    

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def generate_with_retry(prompt, max_retries=3):
    for attempt in range(max_retries):
        try:
            print(f"Attempt {attempt + 1} — calling Groq...")
            response = groq_client.chat.completions.create(
                model="openai/gpt-oss-20b",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4096
            )
            print(f"Success on attempt {attempt + 1}")
            return response.choices[0].message.content
        except Exception as e:
            print(f"EXACT ERROR: {str(e)}")
            if "429" in str(e) or "rate" in str(e).lower():
                wait_time = 15 * (attempt + 1)
                print(f"Rate limit hit, waiting {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise e
    raise Exception("Max retries exceeded. Please try again later.")

def generate_fast(prompt, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048
            )
            return response.choices[0].message.content
        except Exception as e:
            if "429" in str(e) or "rate" in str(e).lower():
                wait_time = 15 * (attempt + 1)
                print(f"Rate limit hit, waiting {wait_time}s...")
                time.sleep(wait_time)
            else:
                print(f"EXACT ERROR: {str(e)}")
                raise e
    raise Exception("Max retries exceeded. Please try again later.")