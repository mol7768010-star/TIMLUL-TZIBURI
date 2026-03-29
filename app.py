import os
import logging
import requests
from flask import Flask, request

# הגדרת לוגים בסיסיים לשרת
logging.basicConfig(level=logging.INFO)
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
        return f"Error: {str(e)}"

@app.route("/transcribe", methods=["GET"])
def transcribe():
    # שליפת פרמטרים
    token = request.args.get('token')
    k_path = request.args.get('K')
    m_param = request.args.get('M', '5')
    n_param = request.args.get('N')
    api_id = request.args.get('ApiCallId')
    ok_val = request.args.get('OK')
    log_enabled = request.args.get('LOG') == "1"

    if not api_id:
        return "Missing ApiCallId", 400

    # פונקציית עזר להדפסת לוגים רק אם LOG=1
    def log_info(msg):
        if log_enabled:
            logging.info(f"[USER-LOG] {msg}")

    text_storage = os.path.join(TEMP_DIR, f"trans_{api_id}.txt")
    ignore_flag = os.path.join(TEMP_DIR, f"ignore_{api_id}.txt")

    # בדיקת דגל התעלמות מ-OK=2 קודם
    if os.path.exists(ignore_flag):
        log_info(f"Detected ignore flag for ApiCallId {api_id}. Resetting OK value.")
        os.remove(ignore_flag)
        ok_val = None

    # --- שלב 2: אישור המשתמש (OK=1) ---
    if ok_val == "1":
        if os.path.exists(text_storage) and token and n_param:
            with open(text_storage, "r", encoding="utf-8") as f:
                final_text = f.read()
            
            orig_filename = k_path.split('/')[-1] if k_path else "recorded.wav"
            upload_path = f"ivr2:{n_param}/{orig_filename.replace('.wav', '.tts')}"

            # העלאה ל-Call2All
            upload_url = "https://www.call2all.co.il/ym/api/UploadTextFile"
            params = {"token": token, "path": upload_path, "content": final_text}
            
            log_info(f"Sending Upload request to: {upload_url} with params: {params}")
            response = requests.get(upload_url, params=params)
            log_info(f"Call2All Response: {response.status_code} - {response.text}")

            if os.path.exists(text_storage): os.remove(text_storage)
            return "id_list_message=m-1452." # סיומת נקודה לבקשתך

        return "id_list_message=f-Error_No_Text."

    elif ok_val == "2":
        log_info(f"User requested re-recording (OK=2). Setting ignore flag.")
        with open(ignore_flag, "w") as f: f.write("1")
        return f"read=m-1012=K,,record,{m_param},,no"

    # --- שלב 1: הקלטה או תמלול ---
    if not k_path:
        log_info("No K parameter. Sending to record.")
        return f"read=m-1012=K,,record,{m_param},,no"

    # תמלול הקובץ
    download_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={token}&path=ivr2:{k_path}"
    log_info(f"Downloading audio from: {download_url}")
    
    try:
        audio_response = requests.get(download_url)
        if audio_response.status_code != 200:
            log_info(f"Download failed with status: {audio_response.status_code}")
            return "id_list_message=f-Error_Downloading."

        temp_audio_path = os.path.join(TEMP_DIR, f"audio_{api_id}.wav")
        with open(temp_audio_path, "wb") as f:
            f.write(audio_response.content)

        transcribed_text = recognize_speech(temp_audio_path)
        if os.path.exists(temp_audio_path): os.remove(temp_audio_path)

        if not transcribed_text or "Error" in transcribed_text:
            log_info(f"Transcription failed or empty: {transcribed_text}")
            return "id_list_message=f-Error_Transcription."

        log_info(f"Transcription success: {transcribed_text}")
        with open(text_storage, "w", encoding="utf-8") as f:
            f.write(transcribed_text)

        # פורמט TTS מעודכן: הטקסט לפני הקובץ מ-1078
        return f"read=t-{transcribed_text}.m-1078=OK,,1,1,,NO,,,,12,,,,,no"

    except Exception as e:
        log_info(f"Exception occurred: {str(e)}")
        return f"Error: {str(e)}"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
