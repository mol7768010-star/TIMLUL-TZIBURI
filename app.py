import os
import requests
from flask import Flask, request

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

def get_next_file_name(token, folder_path):
    url = "https://www.call2all.co.il/ym/api/GetIVR2DirStats"
    params = {"token": token, "path": f"ivr2:{folder_path}"}
    try:
        response = requests.get(url, params=params)
        data = response.json()
        if data.get("responseStatus") == "OK" and data.get("maxFile", {}).get("exists"):
            max_name = data["maxFile"]["name"]
            name_without_ext = max_name.split('.')[0]
            if name_without_ext.isdigit():
                return f"{int(name_without_ext) + 1:03d}.tts"
        return "000.tts"
    except:
        return "error_name.tts"

@app.route("/transcribe", methods=["GET"])
def transcribe():
    token = request.args.get('token', '')
    k_path = request.args.get('K', '')
    m_param = request.args.get('M', '5')
    n_param = request.args.get('N', '')
    path_param = request.args.get('path', '')
    api_id = request.args.get('ApiCallId', '')
    ok_val = request.args.get('OK', '')

    if not api_id: return "Missing ApiCallId", 400

    # הגדרת נתיבי דגלים וקבצים
    text_storage = os.path.join(TEMP_DIR, f"trans_{api_id}.txt")
    flag_a = os.path.join(TEMP_DIR, f"flag_a_{api_id}.txt")
    flag_b = os.path.join(TEMP_DIR, f"flag_b_{api_id}.txt")

    # --- לוגיקה לפי השלבים שביקשת ---

    # 1. טיפול בבקשת OK=2 (הקלטה מחדש)
    if ok_val == "2":
        # מסמנים דגל A, מוחקים דגל B (אם היה) ושולחים להקלטה
        with open(flag_a, "w") as f: f.write("active")
        if os.path.exists(flag_b): os.remove(flag_b)
        return f"read=m-1012=K,,record,{m_param},,no"

    # 2. אם קיים דגל A (אנחנו אחרי לחיצה על 2 וממתינים להקלטה חדשה)
    if os.path.exists(flag_a) and k_path:
        # מבצעים תמלול והחלפה של הקובץ הישן
        download_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={token}&path=ivr2:{k_path}"
        audio_res = requests.get(download_url)
        if audio_res.status_code == 200:
            temp_audio = os.path.join(TEMP_DIR, f"audio_{api_id}.wav")
            with open(temp_audio, "wb") as f: f.write(audio_res.content)
            
            text = recognize_speech(temp_audio)
            if os.path.exists(temp_audio): os.remove(temp_audio)

            if "ERROR_SR" not in text:
                # שומרים את התמלול החדש
                with open(text_storage, "w", encoding="utf-8") as f: f.write(text)
                
                # עוברים למצב דגל B (ממתינים לאישור התמלול החדש)
                with open(flag_b, "w") as f: f.write("active")
                if os.path.exists(flag_a): os.remove(flag_a)
                
                return f"read=t-{text}.m-1078=OK,,1,1,,NO,,,,12,,,,,no"

    # 3. אם קיים דגל B (התמלול החדש מוכן ומחכה ל-OK=1)
    if os.path.exists(flag_b) and ok_val == "1":
        if os.path.exists(text_storage):
            with open(text_storage, "r", encoding="utf-8") as f:
                final_text = f.read()
            
            # בחירת נתיב שמירה
            if path_param:
                filename = get_next_file_name(token, path_param)
                upload_path = f"ivr2:{path_param}/{filename}"
            else:
                orig_name = k_path.split('/')[-1] if k_path else "file.wav"
                upload_path = f"ivr2:{n_param}/{orig_name.replace('.wav', '.tts')}"

            up_url = "https://www.call2all.co.il/ym/api/UploadTextFile"
            up_res = requests.get(up_url, params={"token": token, "what": upload_path, "contents": final_text})
            
            if up_res.status_code == 200:
                # ניקוי סופי של כל הדגלים
                for f in [text_storage, flag_a, flag_b]:
                    if os.path.exists(f): os.remove(f)
                return "id_list_message=m-1452."

    # 4. מצב התחלתי (פעם ראשונה בשיחה - אין דגלים ואין OK)
    if not k_path and not os.path.exists(flag_a) and not os.path.exists(flag_b):
        return f"read=m-1012=K,,record,{m_param},,no"

    # 5. תמלול פעם ראשונה (לפני שהשתמשו ב-OK)
    if k_path and not os.path.exists(flag_a) and not os.path.exists(flag_b):
        # לוגיקת תמלול רגילה לסבב הראשון
        download_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={token}&path=ivr2:{k_path}"
        audio_res = requests.get(download_url)
        if audio_res.status_code == 200:
            temp_audio = os.path.join(TEMP_DIR, f"audio_{api_id}.wav")
            with open(temp_audio, "wb") as f: f.write(audio_res.content)
            text = recognize_speech(temp_audio)
            if os.path.exists(temp_audio): os.remove(temp_audio)
            
            with open(text_storage, "w", encoding="utf-8") as f: f.write(text)
            # המערכת מחכה ל-OK, אז זה כמו מצב B זמני
            with open(flag_b, "w") as f: f.write("active") 
            return f"read=t-{text}.m-1078=OK,,1,1,,NO,,,,12,,,,,no"

    return "id_list_message=f-Error_General."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
