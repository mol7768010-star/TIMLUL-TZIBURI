import os
import requests
import speech_recognition as sr

TEMP_DIR = "/tmp/"

def recognize_speech(file_path):
    recognizer = sr.Recognizer()
    with sr.AudioFile(file_path) as source:
        audio = recognizer.record(source)
    return recognizer.recognize_google(audio, language="he-IL")

def process_call(token, token_g, path, google_url):
    # 1️⃣ קבלת רשימת הקבצים
    stats_url = f"https://www.call2all.co.il/ym/api/GetIVR2DirStats?token={token}&path=ivr2:{path}"
    r = requests.get(stats_url)
    data = r.json()
    if data["responseStatus"] != "OK" or "maxFile" not in data:
        return f"Error listing files: {r.text}"

    max_file_path = data["maxFile"]["path"]
    
    # 2️⃣ הורדת הקובץ האחרון
    download_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={token}&path=ivr2:{max_file_path}"
    audio_response = requests.get(download_url)
    if audio_response.status_code != 200:
        return f"Error downloading file: {audio_response.status_code}"

    temp_audio_path = os.path.join(TEMP_DIR, max_file_path.split('/')[-1])
    with open(temp_audio_path, "wb") as f:
        f.write(audio_response.content)

    # 3️⃣ תמלול
    try:
        text = recognize_speech(temp_audio_path)
    except Exception as e:
        return f"Error in transcription: {e}"
    finally:
        os.remove(temp_audio_path)

    # 4️⃣ שליחת הטקסט ל־Google Chat
    chat_payload = {
        "text": text
    }
    chat_response = requests.post(google_url, json=chat_payload, params={"token": token_g})
    return f"Sent to Google Chat, status: {chat_response.status_code}"
