import os
import logging
import requests
from flask import Flask, request

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
    except Exception:
        return ""

@app.route("/transcribe", methods=["GET"])
def transcribe():
    # שליפת פרמטרים
    token = request.args.get('token')
    k_path = request.args.get('K')
    m_param = request.args.get('M') # חובה - תגובה ראשונית
    n_param = request.args.get('N') # חובה - נתיב שמירה סופי
    api_id = request.args.get('ApiCallId')
    ok_val = request.args.get('OK')

    if not m_param or not api_id:
        return "Missing M or ApiCallId", 400

    # הגדרת נתיבי קבצים זמניים מבוססי ApiCallId
    text_file = os.path.join(TEMP_DIR, f"trans_{api_id}.txt")
    ignore_file = os.path.join(TEMP_DIR, f"ignore_{api_id}.txt")

    # --- שלב בדיקת התעלמות מ-OK=2 קודם ---
    if os.path.exists(ignore_file):
        os.remove(ignore_file) # מוחקים את הדגל לפעם הבאה
        ok_val = None # מבטלים את השפעת ה-OK הנוכחי

    # --- לוגיקה של שלב 2 (אישור/דחייה) ---
    if ok_val == "1":
        # המשתמש אישר - שמירה סופית ל-N
        if os.path.exists(text_file):
            with open(text_file, "r", encoding="utf-8") as f:
                saved_text = f.read()
            
            # בניית נתיב השמירה מתוך שם הקובץ המקורי ב-K
            file_name = k_path.split('/')[-1] if k_path else "file.wav"
            final_path = f"ivr2:{n_param}/{file_name.replace('.wav', '.tts')}"

            upload_url = "https://www.call2all.co.il/ym/api/UploadTextFile"
            requests.get(upload_url, params={"token": token, "path": final_path, "content": saved_text})
            
            # ניקוי
            if os.path.exists(text_file): os.remove(text_file)
            return "id_list_message=f-הקובץ_נשמר_בהצלחה&"
        return "id_list_message=f-שגיאה_לא_נמצא_טקסט&"

    elif ok_val == "2":
        # המשתמש ביקש להקליט מחדש
        # יוצרים קובץ "התעלמות" כדי שבקריאה הבאה (שתכיל OK=2 ב-URL) לא ניכנס לפה שוב
        with open(ignore_file, "w") as f: f.write("1")
        # חוזר לתגובה ראשונית (הקלטה)
        return f"read=m-1012=NAME,,record,{m_param},,no"

    # --- שלב 1: הקלטה ראשונית או תמלול ---
    if not k_path:
        # פעם ראשונה - בקשת הקלטה לנתיב M
        return f"read=m-1012=NAME,,record,{m_param},,no"

    # אם יש K, סימן שהקלטנו ועכשיו מתמללים
    download_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={token}&path=ivr2:{k_path}"
    
    try:
        response = requests.get(download_url)
        if response.status_code != 200:
            return "id_list_message=f-שגיאה_בהורדת_הקובץ&"

        audio_temp = os.path.join(TEMP_DIR, f"audio_{api_id}.wav")
        with open(audio_temp, "wb") as f:
            f.write(response.content)

        text = recognize_speech(audio_temp)
        if os.path.exists(audio_temp): os.remove(audio_temp)

        if not text:
            return "id_list_message=f-לא_הצלחתי_לתמלל&"

        # שמירת הטקסט לזיכרון זמני
        with open(text_file, "w", encoding="utf-8") as f:
            f.write(text)

        # הקראת התמלול למשתמש ובקשת אישור (OK)
        return f"read=m-1078.t-{text}=OK,,1,1,,NO,,,,12,,,,,no"

    except Exception as e:
        return f"Error: {str(e)}"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
