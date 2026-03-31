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

@app.route("/transcribe", methods=["GET"])
def transcribe():
    token = request.args.get('token', '')
    api_id = request.args.get('ApiCallId', '')
    path_param = request.args.get('path', '')
    n_param = request.args.get('N', '')
    m_param = request.args.get('M', '')
    
    if not api_id: return "Missing ApiCallId", 400

    # קבצי ניהול מצב לפי מזהה שיחה
    text_storage = os.path.join(TEMP_DIR, f"trans_{api_id}.txt")
    k_counter_file = os.path.join(TEMP_DIR, f"k_count_{api_id}.txt")

    def get_k_count():
        if not os.path.exists(k_counter_file): return 1
        with open(k_counter_file, "r") as f: 
            try: return int(f.read().strip())
            except: return 1

    def set_k_count(val):
        with open(k_counter_file, "w") as f: f.write(str(val))

    current_k_num = get_k_count()
    
    # בדיקת ה-OK הספציפי לסבב הנוכחי
    current_ok_val = request.args.get(f'OK{current_k_num}', '')
    # בדיקת האם הגיע קובץ הקלטה לסבב הנוכחי
    current_k_path = request.args.get(f'K{current_k_num}', '')

    # --- שלב 1: סיום ושמירה (הקשה על 1) ---
    if current_ok_val == "1":
        if os.path.exists(text_storage):
            with open(text_storage, "r", encoding="utf-8") as f:
                final_text = f.read()
            
            target = path_param if path_param else n_param
            # קביעת שם הקובץ הסופי
            url_stats = "https://www.call2all.co.il/ym/api/GetIVR2DirStats"
            res_stats = requests.get(url_stats, params={"token": token, "path": f"ivr2:{target}"}).json()
            
            filename = "000.tts"
            if res_stats.get("responseStatus") == "OK" and res_stats.get("maxFile", {}).get("exists"):
                name = res_stats["maxFile"]["name"].split('.')[0]
                if name.isdigit(): filename = f"{int(name) + 1:03d}.tts"
            
            upload_path = f"ivr2:{target}/{filename}"
            requests.get("https://www.call2all.co.il/ym/api/UploadTextFile", 
                         params={"token": token, "what": upload_path, "contents": final_text})
            
            # ניקוי
            if os.path.exists(text_storage): os.remove(text_storage)
            if os.path.exists(k_counter_file): os.remove(k_counter_file)
            return "id_list_message=m-1452."

    # --- שלב 2: בקשת תיקון (הקשה על 2) ---
    if current_ok_val == "2":
        new_k_num = current_k_num + 1
        set_k_count(new_k_num)
        # שולח להקלטה חדשה עם משתנה K הבא
        return f"read=m-1012=K{new_k_num},,record,{m_param},,no"

    # --- שלב 3: עיבוד הקלטה קיימת ---
    if current_k_path:
        down_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={token}&path=ivr2:{current_k_path}"
        res = requests.get(down_url)
        if res.status_code == 200:
            audio_tmp = os.path.join(TEMP_DIR, f"audio_{api_id}.wav")
            with open(audio_tmp, "wb") as f: f.write(res.content)
            text = recognize_speech(audio_tmp)
            if os.path.exists(audio_tmp): os.remove(audio_tmp)
            
            with open(text_storage, "w", encoding="utf-8") as f: f.write(text)
            
            # כאן אנחנו מגדירים שהתשובה (1 או 2) תחזור למשתנה OK שמתאים למספר ה-K
            return f"read=t-{text}.m-1078=OK{current_k_num},,1,1,,NO,,,,12,,,,,no"

    # --- שלב 0: התחלה ראשונית ---
    if not current_k_path and not current_ok_val:
        set_k_count(1)
        return f"read=m-1012=K1,,record,{m_param},,no"

    return "id_list_message=f-Error_General."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
