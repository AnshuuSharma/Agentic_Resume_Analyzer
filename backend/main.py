from flask import Flask, request, jsonify
from flask_cors import CORS
from utils import extract_text_from_file
from agent import app as graph_app
import uuid

flask_app = Flask(__name__)
CORS(flask_app)

@flask_app.route('/analyze', methods=['POST'])
def analyze():

   try:
        if 'resume' not in request.files:
         return jsonify({"error": "resume file is missing"}), 400
    
    
        if 'jd_text' not in request.form:
         return jsonify({"error": "jd_text is missing"}), 400
    
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
        "user_message": "",
        "tool_calls": [],
        "tool_results": {}
        }, config=config)
    
        return jsonify({
        "analysis": result["analysis"],
        "session_id": session_id  
        })
   except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500

@flask_app.route('/chat', methods=['POST'])
def chat():
    data = request.json

    if not data.get('message'):
        return jsonify({"error": "message is missing"}), 400
    if not data.get('session_id'):
        return jsonify({"error": "session_id is missing"}), 400
    
    
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