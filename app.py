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
    token = request.args.get("token")
    token_g = request.args.get("token_g")
    api_id = request.args.get("ApiCallId")

    if not token or not token_g or not api_id:
        return jsonify({"status": "error", "message": "Missing required parameters"}), 400

    path = "111"  # תמיד תיקייה 111

    # --- שלב 1: קבלת נתוני התיקייה ב-Call2All ---
    stats_url = f"https://www.call2all.co.il/ym/api/GetIVR2DirStats?token={token}&path=ivr2:{path}"
    try:
        stats_resp = requests.get(stats_url)
        stats = stats_resp.json()
    except Exception as e:
        return jsonify({"status": "error", "message": f"Error fetching directory stats: {str(e)}"}), 500

    if stats.get("responseStatus") != "OK" or "maxFile" not in stats:
        return jsonify({"status": "error", "message": "No files found in directory"}), 500

    max_file_path = stats["maxFile"]["path"]  # למשל "111/374.wav"
    download_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={token}&path=ivr2:{max_file_path}"

    # --- שלב 2: הורדת הקובץ ---
    try:
        audio_resp = requests.get(download_url)
        if audio_resp.status_code != 200:
            return jsonify({"status": "error", "message": "Failed to download audio"}), 500
        temp_audio = os.path.join(TEMP_DIR, f"audio_{api_id}.wav")
        with open(temp_audio, "wb") as f:
            f.write(audio_resp.content)
    except Exception as e:
        return jsonify({"status": "error", "message": f"Download error: {str(e)}"}), 500

    # --- שלב 3: תמלול ---
    text = recognize_speech(temp_audio)
    if os.path.exists(temp_audio):
        os.remove(temp_audio)

    if "ERROR_SR" in text:
        return jsonify({"status": "error", "message": "Error in transcription"}), 500

    # --- שלב 4: שליחה ל-Google Chat ---
    chat_url = f"https://chat.googleapis.com/v1/spaces/AAQAWjjfDoU/messages?key=AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI&token={token_g}"
    try:
        chat_resp = requests.post(chat_url, json={"text": text})
        chat_status = chat_resp.status_code
    except Exception as e:
        return jsonify({"status": "error", "message": f"Error sending to Google Chat: {str(e)}"}), 500

    return jsonify({
        "status": "ok",
        "transcribed_text": text,
        "google_chat_status": chat_status
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
