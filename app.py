import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)
TEMP_DIR = "/tmp/"

def recognize_speech(file_path):
    import speech_recognition as sr
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(file_path) as source:
            audio = recognizer.record(source)
        return recognizer.recognize_google(audio, language="he-IL")
    except Exception as e:
        return f"ERROR_SR: {str(e)}"

@app.route("/transcribe", methods=["GET"])
def transcribe():
    # --- קריאת פרמטרים ---
    api_id = request.args.get("ApiCallId")
    token = request.args.get("token")
    token_g = request.args.get("token_g")
    url_external = request.args.get("URL")
    path_dir = request.args.get("path")

    if not api_id or not token or not token_g or not url_external or not path_dir:
        return "Missing required parameters", 400

    # --- שלב 1: קבלת מידע על התיקייה והקובץ האחרון ---
    stats_url = f"https://www.call2all.co.il/ym/api/GetIVR2DirStats?token={token}&path=ivr2:{path_dir}"
    try:
        stats_resp = requests.get(stats_url)
        stats_resp.raise_for_status()
        stats_json = stats_resp.json()
        max_file = stats_json.get("maxFile", {})
        if not max_file or not max_file.get("exists"):
            return "No audio file found", 404
        audio_path = max_file["path"]  # לדוגמה: 111/374.wav
    except Exception as e:
        return f"Error fetching directory stats: {str(e)}", 500

    # --- שלב 2: הורדת הקובץ ---
    download_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={token}&path=ivr2:{audio_path}"
    temp_audio_path = os.path.join(TEMP_DIR, f"audio_{api_id}.wav")
    try:
        audio_resp = requests.get(download_url)
        audio_resp.raise_for_status()
        with open(temp_audio_path, "wb") as f:
            f.write(audio_resp.content)
    except Exception as e:
        return f"Error downloading audio: {str(e)}", 500

    # --- שלב 3: תמלול הקובץ ---
    text = recognize_speech(temp_audio_path)
    if os.path.exists(temp_audio_path):
        os.remove(temp_audio_path)

    if "ERROR_SR" in text:
        return "Error in transcription", 500

    # --- שלב 4: שליחת הטקסט ל-Google Chat ---
    chat_url = f"https://chat.googleapis.com/v1/spaces/AAQAWjjfDoU/messages?key=AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI&token={token_g}"
    try:
        chat_resp = requests.post(chat_url, json={"text": text})
    except Exception as e:
        chat_resp = None

    # --- שלב 5: שליחת GET ל-URL חיצוני עם כל הפרמטרים שקיבלנו מלבד token/token_g/URL ---
    params_to_send = {k: v for k, v in request.args.items() if k not in ["token", "token_g", "URL"]}
    params_to_send["transcribed_text"] = text
    try:
        ext_resp = requests.get(url_external, params=params_to_send)
    except Exception as e:
        ext_resp = None

    # --- שלב 6: החזרת סטטוס ---
    return jsonify({
        "google_chat_status": chat_resp.status_code if chat_resp else "error",
        "external_url_status": ext_resp.status_code if ext_resp else "error",
        "status": "ok",
        "transcribed_text": text
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
