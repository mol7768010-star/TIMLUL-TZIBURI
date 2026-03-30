import os
import requests
import speech_recognition as sr
from flask import Flask, request, jsonify

app = Flask(__name__)
TEMP_DIR = "/tmp/"

def recognize_speech(file_path):
    recognizer = sr.Recognizer()
    with sr.AudioFile(file_path) as source:
        audio = recognizer.record(source)
    return recognizer.recognize_google(audio, language="he-IL")

@app.route("/transcribe", methods=["GET"])
def transcribe():
    token = request.args.get("token")
    token_g = request.args.get("token_g")
    url_external = request.args.get("URL")
    path = request.args.get("path")
    api_call_id = request.args.get("ApiCallId")
    
    if not all([token, token_g, url_external, path, api_call_id]):
        return "Missing required parameters", 400

    # 1️⃣ קבלת הקובץ האחרון
    stats_url = f"https://www.call2all.co.il/ym/api/GetIVR2DirStats?token={token}&path=ivr2:{path}"
    r = requests.get(stats_url)
    try:
        data = r.json()
        max_file_path = data["maxFile"]["path"]
    except Exception:
        return f"Error listing files: {r.text}", 500

    # 2️⃣ הורדת הקובץ האחרון
    download_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={token}&path=ivr2:{max_file_path}"
    audio_resp = requests.get(download_url)
    if audio_resp.status_code != 200:
        return f"Error downloading file: {audio_resp.status_code}", 500

    temp_file = os.path.join(TEMP_DIR, max_file_path.split("/")[-1])
    with open(temp_file, "wb") as f:
        f.write(audio_resp.content)

    # 3️⃣ תמלול
    try:
        text = recognize_speech(temp_file)
    except Exception as e:
        os.remove(temp_file)
        return f"Error in transcription: {e}", 500
    os.remove(temp_file)

    # 4️⃣ שליחה ל־Google Chat
    chat_payload = {"text": text}
    chat_response = requests.post(url_external, json=chat_payload, params={"token": token_g})

    # 5️⃣ שליחת פרמטרים ל־URL חיצוני
    params_to_send = {k: v for k, v in request.args.items() if k not in ["token", "token_g", "URL"]}
    try:
        requests.get(url_external, params=params_to_send)
    except Exception:
        pass  # לא נחסם אם נכשל

    return jsonify({
        "status": "ok",
        "transcribed_text": text,
        "google_chat_status": chat_response.status_code
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
