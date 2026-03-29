import os
import tempfile
import logging
import requests
from flask import Flask, request, jsonify
import speech_recognition as sr

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

def recognize_speech(file_path):
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(file_path) as source:
            audio = recognizer.record(source)
        return recognizer.recognize_google(audio, language="he-IL")
    except Exception:
        return ""

@app.route("/transcribe", methods=["GET"])
def transcribe():
    # קבלת פרמטרים
    token = request.args.get('token')
    k_path = request.args.get('K')
    m_param = request.args.get('M', '') # תוכן הפרמטר M
    n_param = request.args.get('N')

    # בדיקה אם חסר פרמטר K
    if not k_path:
        return f"read=m-1012=NAME,,record,{m_param},,no"

    if not token:
        return "Missing token", 400

    # בניית נתיב ההורדה
    download_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={token}&path=ivr2:{k_path}"
    
    try:
        # הורדת הקובץ
        response = requests.get(download_url)
        if response.status_code != 200:
            return "Failed to download file", 500

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
            temp_audio.write(response.content)
            temp_path = temp_audio.name

        # תמלול
        text = recognize_speech(temp_path)
        os.remove(temp_path)

        # לוגיקה לבניית נתיב השמירה (Upload)
        path_parts = k_path.split('/')
        file_name = path_parts[-1]
        
        if n_param:
            upload_path = f"ivr2:{n_param}/{file_name.replace('.wav', '.tts')}"
        else:
            upload_path = f"ivr2:{k_path.replace('.wav', '.tts')}"

        # העלאת הטקסט חזרה
        upload_url = "https://www.call2all.co.il/ym/api/UploadTextFile"
        upload_params = {
            "token": token,
            "path": upload_path,
            "content": text
        }
        requests.get(upload_url, params=upload_params)

        # החזרת תשובה
        return text if text else "No transcription"

    except Exception as e:
        return f"Error: {str(e)}", 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
