import os
import logging
import requests
from flask import Flask, request

# הגדרת לוגים למעקב
logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

# תיקייה זמנית בשרת Render לאחסון נתונים במהלך השיחה
TEMP_DIR = "/tmp/"

def recognize_speech(file_path):
    """פונקציה לביצוע תמלול באמצעות Google Speech Recognition"""
    import speech_recognition as sr
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(file_path) as source:
            audio = recognizer.record(source)
        # תמלול לעברית
        return recognizer.recognize_google(audio, language="he-IL")
    except Exception as e:
        logging.error(f"Speech recognition error: {e}")
        return ""

@app.route("/transcribe", methods=["GET"])
def transcribe():
    # שליפת פרמטרים מה-URL
    token = request.args.get('token')
    k_path = request.args.get('K')     # נתיב הקובץ שהוקלט
    m_param = request.args.get('M', '5') # תיקיית הקלטה (ברירת מחדל 5)
    n_param = request.args.get('N')     # תיקיית יעד לשמירת ה-TTS
    api_id = request.args.get('ApiCallId')
    ok_val = request.args.get('OK')

    # בדיקת פרמטרים חיוניים
    if not api_id:
        return "Missing ApiCallId", 400

    # הגדרת נתיבי קבצים זמניים מבוססי ApiCallId כדי למנוע ערבוב בין שיחות
    text_storage = os.path.join(TEMP_DIR, f"trans_{api_id}.txt")
    ignore_flag = os.path.join(TEMP_DIR, f"ignore_{api_id}.txt")

    # --- לוגיקה לטיפול ב-OK=2 (התעלמות מהפרמטר בקריאה הבאה) ---
    if os.path.exists(ignore_flag):
        logging.info(f"Ignoring old OK value for ApiCallId: {api_id}")
        os.remove(ignore_flag)
        ok_val = None # מבטל את ה-OK הנוכחי כי הוא "שארית" מהסיבוב הקודם

    # --- שלב 2: עיבוד בחירת המשתמש (אישור או הקלטה מחדש) ---
    if ok_val == "1":
        # המשתמש אישר את התמלול - שמירה סופית לשרת Call2All
        if os.path.exists(text_storage) and token and n_param:
            with open(text_storage, "r", encoding="utf-8") as f:
                final_text = f.read()
            
            # חילוץ שם הקובץ המקורי ושמירה בסיומת .tts בתיקייה N
            orig_filename = k_path.split('/')[-1] if k_path else "recorded.wav"
            upload_path = f"ivr2:{n_param}/{orig_filename.replace('.wav', '.tts')}"

            # שליחת הטקסט לשרת Call2All (דחיפת ה-TTS)
            upload_url = "https://www.call2all.co.il/ym/api/UploadTextFile"
            requests.get(upload_url, params={
                "token": token, 
                "path": upload_path, 
                "content": final_text
            })
            
            # ניקוי קבצים זמניים
            if os.path.exists(text_storage): os.remove(text_storage)
            return "id_list_message=m-1452&" # תגובה סופית
        return "id_list_message=f-Error_No_Text&"

    elif ok_val == "2":
        # המשתמש בחר להקליט מחדש
        with open(ignore_flag, "w") as f: f.write("ignore")
        return f"read=m-1012=K,,record,{m_param},,no"

    # --- שלב 1: הקלטה או תמלול ראשוני ---
    if not k_path:
        # פעם ראשונה בשלוחה - שליחה להקלטה
        return f"read=m-1012=K,,record,{m_param},,no"

    # אם יש K, סימן שהקובץ הוקלט - מתחילים תמלול
    if not token: return "Missing Token", 400
    
    download_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={token}&path=ivr2:{k_path}"
    
    try:
        # הורדת קובץ השמע זמנית
        audio_response = requests.get(download_url)
        if audio_response.status_code != 200:
            return "id_list_message=f-Error_Downloading&"

        temp_audio_path = os.path.join(TEMP_DIR, f"audio_{api_id}.wav")
        with open(temp_audio_path, "wb") as f:
            f.write(audio_response.content)

        # ביצוע התמלול
        transcribed_text = recognize_speech(temp_audio_path)
        if os.path.exists(temp_audio_path): os.remove(temp_audio_path)

        if not transcribed_text:
            return "id_list_message=f-לא_הצלחתי_לתמלל_נסה_שנית&"

        # שמירת הטקסט בשרת עד לקבלת אישור OK=1
        with open(text_storage, "w", encoding="utf-8") as f:
            f.write(transcribed_text)

        # החזרת פלט TTS להקראה ואישור המשתמש
        return f"read=m-1078.t-{transcribed_text}=OK,,1,1,,NO,,,,12,,,,,no"

    except Exception as e:
        logging.error(f"General error: {e}")
        return f"Error: {str(e)}"

if __name__ == "__main__":
    # הגדרת הפורט עבור Render
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
