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
            name = data["maxFile"]["name"].split('.')[0]
            if name.isdigit(): return f"{int(name) + 1:03d}.tts"
        return "000.tts"
    except: return "error_name.tts"

@app.route("/transcribe", methods=["GET"])
def transcribe():
    # --- פרמטרים ---
    token = request.args.get('token', '')
    k_path = request.args.get('K', '')
    api_id = request.args.get('ApiCallId', '')
    ok_val = request.args.get('OK', '')
    n_param = request.args.get('N', '')
    path_param = request.args.get('path', '')
    m_param = request.args.get('M', '')
    
    if not api_id: return "Missing ApiCallId", 400

    # --- קבצי ניהול מצב ---
    flag_file = os.path.join(TEMP_DIR, f"state_{api_id}.txt") # שומר A, B, C, D
    text_storage = os.path.join(TEMP_DIR, f"trans_{api_id}.txt")
    processed_k_file = os.path.join(TEMP_DIR, f"k_list_{api_id}.txt")

    def get_state():
        if not os.path.exists(flag_file): return None
        with open(flag_file, "r") as f: return f.read().strip()

    def set_state(state):
        with open(flag_file, "w") as f: f.write(state)

    def is_k_processed(k):
        if not os.path.exists(processed_k_file): return False
        with open(processed_k_file, "r") as f: return k in f.read().splitlines()

    def add_k_to_list(k):
        with open(processed_k_file, "a") as f: f.write(k + "\n")

    current_state = get_state()

    # --- שלב 3 & 5: טיפול ב-OK=1 / OK=2 ---
    if ok_val == "1" and current_state in ["B", "D"]:
        if os.path.exists(text_storage):
            with open(text_storage, "r", encoding="utf-8") as f:
                final_text = f.read()
            
            target = path_param if path_param else n_param
            filename = get_next_file_name(token, target) if path_param else k_path.split('/')[-1].replace('.wav', '.tts')
            upload_path = f"ivr2:{target}/{filename}"
            
            requests.get("https://www.call2all.co.il/ym/api/UploadTextFile", 
                         params={"token": token, "what": upload_path, "contents": final_text})
            
            # ניקוי סופי
            for f in [flag_file, text_storage, processed_k_file]:
                if os.path.exists(f): os.remove(f)
            return "id_list_message=m-1452."

    if ok_val == "2" and current_state in ["B", "D"]:
        set_state("C")
        return f"read=m-1012=K,,record,{m_param},,no"

    # --- שלב 2, 4 & 6: הגעת K חדש (תמלול) ---
    if k_path and not is_k_processed(k_path):
        # תמלול הקובץ
        down_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={token}&path=ivr2:{k_path}"
        res = requests.get(down_url)
        if res.status_code == 200:
            audio_tmp = os.path.join(TEMP_DIR, f"audio_{api_id}.wav")
            with open(audio_tmp, "wb") as f: f.write(res.content)
            text = recognize_speech(audio_tmp)
            os.remove(audio_tmp)
            
            with open(text_storage, "w", encoding="utf-8") as f: f.write(text)
            add_k_to_list(k_path)
            
            # עדכון דגלים לפי הסבב
            if current_state == "C": set_state("D")
            else: set_state("B")
            
            return f"read=t-{text}.m-1078=OK,,1,1,,NO,,,,12,,,,,no"

    # --- שלב 1: התחלה (ללא K) ---
    if not k_path and current_state is None:
        set_state("A")
        return f"read=m-1012=K,,record,5,,no"

    # אם הגענו לכאן בטעות (למשל K ישן שוב), נחזיר את התמלול הקיים
    if os.path.exists(text_storage):
        with open(text_storage, "r", encoding="utf-8") as f:
            text = f.read()
        return f"read=t-{text}.m-1078=OK,,1,1,,NO,,,,12,,,,,no"

    return "id_list_message=f-Error_General."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
