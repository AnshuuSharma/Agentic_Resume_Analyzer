from flask import Flask, request, jsonify
from flask_cors import CORS
from utils import extract_text_from_file, AgentState
from agent import app as graph_app
from nodes import chat_node
import uuid
import traceback

flask_app = Flask(__name__)
CORS(flask_app)

# In memory session store
sessions = {}

@flask_app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})

@flask_app.route('/analyze', methods=['POST'])
def analyze():
    try:
        if 'resume' not in request.files:
            return jsonify({"error": "resume file is missing"}), 400
        if 'jd_text' not in request.form:
            return jsonify({"error": "jd_text is missing"}), 400

        resume_file = request.files['resume']
        jd_text = request.form['jd_text']

        if resume_file.filename == '':
            return jsonify({"error": "no file selected"}), 400

        session_id = str(uuid.uuid4())
        resume_text = extract_text_from_file(resume_file)

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
        })

        sessions[session_id] = {
            "resume_data": result.get("resume_data", {}),
            "jd_data": result.get("jd_data", {}),
            "analysis": result.get("analysis", ""),
            "tool_results": result.get("tool_results", {}),
            "chat_history": []
        }

        print(f"SESSION SAVED: {session_id}")

        print(f"SESSION CREATED: {session_id}")
        print(f"ANALYSIS LENGTH: {len(sessions[session_id]['analysis'])}")
        print(f"RESUME DATA KEYS: {list(sessions[session_id]['resume_data'].keys())}")

        return jsonify({
            "analysis": result["analysis"],
            "session_id": session_id
        })

    except Exception as e:
        print(f"ANALYZE FULL ERROR: {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@flask_app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json

        if not data.get('message'):
            return jsonify({"error": "message is missing"}), 400
        if not data.get('session_id'):
            return jsonify({"error": "session_id is missing"}), 400

        session_id = data['session_id']
        user_message = data['message']

        print(f"AVAILABLE SESSIONS: {list(sessions.keys())}")
        print(f"REQUESTED SESSION: {session_id}")

        if session_id not in sessions:
            return jsonify({"error": "Session not found. Please analyze your resume first."}), 400

        session = sessions[session_id]

        if not session.get("analysis"):
            return jsonify({
                "error": "Session data is empty. Please analyze your resume again."
            }), 400

        state = {
            "resume_text": "",
            "jd_text": "",
            "resume_data": session["resume_data"],
            "jd_data": session["jd_data"],
            "analysis": session["analysis"],
            "tool_results": session["tool_results"],
            "chat_history": session["chat_history"],
            "user_message": user_message,
            "tool_calls": [],
        }

        result = chat_node(state)

        sessions[session_id]["chat_history"] = result["chat_history"]

        chat_history = result.get("chat_history", [])

        if not chat_history:
            return jsonify({"error": "No response generated"}), 500

        return jsonify({
            "response": chat_history[-1]["content"]
        })

    except Exception as e:
        print(f"CHAT FULL ERROR: {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    flask_app.run(debug=True)