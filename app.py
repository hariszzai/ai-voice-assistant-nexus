from flask import Flask, render_template, request, jsonify
from main import process_command_text, speak, voice_assistant_loop, analyze_image, voice_mode_active
from shared import notifications_queue
import pygame
import threading
import os
import requests
from dotenv import load_dotenv
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

def generate_chat_title(message):
    try:
        response = requests.post(
            url="https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": "Generate a short 3-5 word chat title for this message. Return ONLY the title, nothing else, no quotes."},
                    {"role": "user", "content": message}
                ]
            }
        )
        return response.json()["choices"][0]["message"]["content"].strip()
    except:
        return message[:35]

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data["message"]
    source = data.get("source", "text")
    image_data = data.get("image")
    image_type = data.get("image_type")
    if voice_mode_active["value"] and source == "voice":
        return jsonify({"response": ""})
    if image_data:
        response = analyze_image(user_message, image_data, image_type)
    else:
        response = process_command_text(user_message)
    if response and response != "IMAGE_GENERATED":
        from database import save_message
        save_message("default", "user", user_message)
        save_message("default", "assistant", response)
    if source == "voice":
        speak(response)
    return jsonify({"response": response})

@app.route("/get_title", methods=["POST"])
def get_title():
    data = request.get_json()
    title = generate_chat_title(data.get("message", "New Chat"))
    return jsonify({"title": title})

@app.route("/set_voice", methods=["POST"])
def set_voice():
    data = request.get_json()
    from shared import voice_settings
    from database import save_voice_settings
    voice_settings["voice"] = data.get("voice", "en-US-GuyNeural")
    voice_settings["speed"] = data.get("speed", "20")
    save_voice_settings(voice_settings["voice"], voice_settings["speed"])  # persist to DB
    return jsonify({"status": "ok"})

@app.route("/set_profile", methods=["POST"])
def set_profile():
    data = request.get_json()
    from shared import user_profile
    from database import save_profile
    user_profile["name"] = data.get("name", "")
    user_profile["city"] = data.get("city", "")
    save_profile(user_profile["name"], user_profile["city"])  # persist to DB
    return jsonify({"status": "ok"})

@app.route("/stop", methods=["POST"])
def stop():
    try:
        pygame.mixer.music.stop()
    except:
        pass
    return jsonify({"status": "stopped"})

@app.route("/latest_image", methods=["GET"])
def latest_image():
    image_path = os.path.join("static", "generated_image.png")
    if os.path.exists(image_path):
        return jsonify({"available": True, "url": "/static/generated_image.png"})
    return jsonify({"available": False})

@app.route("/is_speaking", methods=["GET"])
def is_speaking():
    try:
        speaking = pygame.mixer.music.get_busy()
        return jsonify({"speaking": bool(speaking)})
    except:
        return jsonify({"speaking": False})

from shared import notifications_queue, custom_system_prompt

@app.route("/set_system_prompt", methods=["POST"])
def set_system_prompt():
    data = request.get_json()
    custom_system_prompt["value"] = data.get("prompt", "")
    return jsonify({"status": "ok"})

@app.route("/notifications", methods=["GET"])
def get_notifications():
    if notifications_queue:
        msg = notifications_queue.pop(0)
        return jsonify({"message": msg})
    return jsonify({"message": None})

if __name__ == "__main__":
    from main import check_reminders
    voice_thread = threading.Thread(target=voice_assistant_loop, daemon=True)
    voice_thread.start()
    reminder_thread = threading.Thread(target=check_reminders, daemon=True)
    reminder_thread.start()
    app.run(debug=False)
    # debug=False is important — debug=True causes Flask to start twice
    # which would launch two voice threads