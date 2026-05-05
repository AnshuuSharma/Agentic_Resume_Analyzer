from flask import Flask, request, jsonify
from flask_cors import CORS
from utils import extract_text_from_file
from agent import app as graph_app
import uuid

flask_app = Flask(__name__)
CORS(flask_app)

@flask_app.route('/analyze', methods=['POST'])
def analyze():
    
    resume_file = request.files['resume']
    jd_text = request.form['jd_text']
    
  
    session_id = str(uuid.uuid4())
    
    
    resume_text = extract_text_from_file(resume_file)
    
    config = {"configurable": {"thread_id": session_id}}
    
    
    result = graph_app.invoke({
        "resume_text": resume_text,
        "jd_text": jd_text,
        "resume_data": {},
        "jd_data": {},
        "analysis": "",
        "chat_history": [],
        "user_message": ""
    }, config=config)
    
    return jsonify({
        "analysis": result["analysis"],
        "session_id": session_id  
    })


@flask_app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data['message']
    session_id = data['session_id']  # frontend sends this back
    
    config = {"configurable": {"thread_id": session_id}}
    
    result = graph_app.invoke({
        "user_message": user_message
    }, config=config)
    
    return jsonify({
        "response": result["chat_history"][-1]["content"]
    })


if __name__ == '__main__':
    flask_app.run(debug=True)