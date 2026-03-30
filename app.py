import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)
TEMP_DIR = "/tmp/"

CALL2ALL_STATS_URL = "https://www.call2all.co.il/ym/api/GetIVR2DirStats"
CALL2ALL_DOWNLOAD_URL = "https://www.call2all.co.il/ym/api/DownloadFile"
GOOGLE_CHAT_WEBHOOK = "https://chat.googleapis.com/v1/spaces/AAQAWjjfDoU/messages?key=AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI"

GOOGLE_APPS_SCRIPT = "https://script.google.com/macros/s/AKfycbzBOXpGWhA0NJbWarVO0kkl9Lx_VnXeAtTKJuV8zadx2ScYXyB10Epe422rceUWOUTaRA/exec"

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
    # שליפת פרמטרים
    token = request.args.get('token', '')
    token_g = request.args.get('token_g', '')
    path_param = request.args.get('path', '')
    api_id = request.args.get('ApiCallId', '')

    if not all([token, token_g, path_param, api_id]):
        return "Missing required parameters", 400

    # --- שליחת GET מיידית ל-Google Apps Script ---
    try:
        apps_resp = requests.get(GOOGLE_APPS_SCRIPT, params={"T": 1, "M": "פייתון"})
        apps_status = apps_resp.status_code
    except Exception as e:
        apps_status = f"error: {str(e)}"

    # --- שלב 1: קבלת מידע על הקבצים ב-Call2All ---
    try:
        stats_resp = requests.get(CALL2ALL_STATS_URL, params={"token": token, "path": f"ivr2:{path_param}"})
        stats_resp.raise_for_status()
        stats_json = stats_resp.json()
        max_file = stats_json["maxFile"]["name"]
    except Exception as e:
        return jsonify({
            "google_apps_script_status": apps_status,
            "status": "error",
            "message": f"Error listing files: {str(e)}"
        })

    # --- הורדת הקובץ האחרון ---
    try:
        download_resp = requests.get(CALL2ALL_DOWNLOAD_URL, params={"token": token, "path": f"ivr2:{path_param}/{max_file}"})
        download_resp.raise_for_status()
        temp_audio = os.path.join(TEMP_DIR, f"audio_{api_id}.wav")
        with open(temp_audio, "wb") as f:
            f.write(download_resp.content)
    except Exception as e:
        return jsonify({
            "google_apps_script_status": apps_status,
            "status": "error",
            "message": f"Error downloading file: {str(e)}"
        })

    # --- תמלול הקובץ ---
    text = recognize_speech(temp_audio)
    if os.path.exists(temp_audio):
        os.remove(temp_audio)
    if "ERROR_SR" in text:
        return jsonify({
            "google_apps_script_status": apps_status,
            "status": "error",
            "message": "Error in transcription"
        })

    # --- שליחת ההודעה ל-Google Chat ---
    chat_status = None
    try:
        chat_resp = requests.post(
            f"{GOOGLE_CHAT_WEBHOOK}&token={token_g}",
            json={"text": text}
        )
        chat_status = chat_resp.status_code
    except Exception as e:
        chat_status = f"error: {str(e)}"

    return jsonify({
        "google_apps_script_status": apps_status,
        "google_chat_status": chat_status,
        "status": "ok",
        "transcribed_text": text
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
