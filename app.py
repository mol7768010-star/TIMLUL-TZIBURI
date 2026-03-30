import os
import requests
from flask import Flask, request, jsonify
import speech_recognition as sr

app = Flask(__name__)
TEMP_DIR = "/tmp/"

def recognize_speech(file_path):
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(file_path) as source:
            audio = recognizer.record(source)
        return recognizer.recognize_google(audio, language="he-IL")
    except Exception as e:
        return f"ERROR_SR: {str(e)}"

@app.route("/transcribe", methods=["GET"])
def transcribe():
    # --- קבלת פרמטרים ---
    token = request.args.get('token')
    token_g = request.args.get('token_g')
    path = request.args.get('path', '111')
    api_id = request.args.get('ApiCallId')

    log = {}

    # --- בדיקות בסיס ---
    if not token or not token_g or not api_id:
        return jsonify({"LO": "Missing required parameters", "sent": dict(request.args)}), 400

    # --- שלב 1: קבלת הקובץ הגבוה ביותר ---
    stats_url = f"https://www.call2all.co.il/ym/api/GetIVR2DirStats?token={token}&path=ivr2:{path}"
    try:
        resp_stats = requests.get(stats_url)
        log['stats_sent'] = stats_url
        log['stats_response'] = resp_stats.text
        resp_json = resp_stats.json()
        max_file = resp_json.get('maxFile')
        if not max_file or not max_file.get('exists'):
            return jsonify({"LO": "No max file found", "sent": stats_url, "response": resp_stats.text})
        max_file_path = max_file['path']
    except Exception as e:
        return jsonify({"LO": f"Failed to get max file: {str(e)}", "sent": stats_url})

    # --- שלב 2: הורדת הקובץ ---
    download_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={token}&path=ivr2:{max_file_path}"
    temp_audio = os.path.join(TEMP_DIR, f"audio_{api_id}.wav")
    try:
        resp_audio = requests.get(download_url)
        log['download_sent'] = download_url
        log['download_status'] = resp_audio.status_code
        log['download_response_len'] = len(resp_audio.content)
        if resp_audio.status_code != 200 or len(resp_audio.content) == 0:
            return jsonify({"LO": "Failed to download audio", "sent": download_url, "response_status": resp_audio.status_code})
        with open(temp_audio, "wb") as f:
            f.write(resp_audio.content)
    except Exception as e:
        return jsonify({"LO": f"Download exception: {str(e)}", "sent": download_url})

    # --- שלב 3: תמלול ---
    try:
        text = recognize_speech(temp_audio)
        log['transcribed_text'] = text
        if os.path.exists(temp_audio):
            os.remove(temp_audio)
        if "ERROR_SR" in text:
            return jsonify({"LO": "Transcription failed", "sent": download_url, "response": text})
    except Exception as e:
        return jsonify({"LO": f"Transcription exception: {str(e)}", "sent": download_url})

    # --- שלב 4: שליחת הטקסט ל-Google Chat ---
    chat_url = f"https://chat.googleapis.com/v1/spaces/AAQAWjjfDoU/messages?key=AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI&token={token_g}"
    chat_payload = {"text": text}
    try:
        resp_chat = requests.post(chat_url, json=chat_payload)
        log['chat_sent'] = chat_url
        log['chat_payload'] = chat_payload
        log['chat_status'] = resp_chat.status_code
        log['chat_response'] = resp_chat.text
        if resp_chat.status_code != 200:
            return jsonify({"LO": "Google Chat send failed", "sent": chat_url, "payload": chat_payload, "response": resp_chat.text})
    except Exception as e:
        return jsonify({"LO": f"Google Chat exception: {str(e)}", "sent": chat_url, "payload": chat_payload})

    # --- הצלחה ---
    return jsonify({"status": "ok", "transcribed_text": text, "log": log})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
