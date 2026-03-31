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
    token = request.args.get('token', '')
    api_id = request.args.get('ApiCallId', '')
    ok_val = request.args.get('OK', '')
    path_param = request.args.get('path', '')
    n_param = request.args.get('N', '')
    m_param = request.args.get('M', '')
    
    if not api_id: return "Missing ApiCallId", 400

    # קבצי ניהול מצב
    flag_file = os.path.join(TEMP_DIR, f"state_{api_id}.txt")
    text_storage = os.path.join(TEMP_DIR, f"trans_{api_id}.txt")
    k_counter_file = os.path.join(TEMP_DIR, f"k_count_{api_id}.txt")

    def get_state():
        if not os.path.exists(flag_file): return None
        with open(flag_file, "r") as f: return f.read().strip()

    def set_state(state):
        with open(flag_file, "w") as f: f.write(state)

    def get_k_count():
        if not os.path.exists(k_counter_file): return 0
        with open(k_counter_file, "r") as f: return int(f.read().strip())

    def inc_k_count():
        count = get_k_count() + 1
        with open(k_counter_file, "w") as f: f.write(str(count))
        return count

    current_state = get_state()
    current_k_num = get_k_count()
    
    # חיפוש האם התקבל K כלשהו (K1, K2, K3...)
    received_k_path = None
    if current_k_num > 0:
        received_k_path = request.args.get(f'K{current_k_num}')

    # --- שלב סיום: OK=1 ---
    if ok_val == "1":
        if os.path.exists(text_storage):
            with open(text_storage, "r", encoding="utf-8") as f:
                final_text = f.read()
            
            target = path_param if path_param else n_param
            # שם הקובץ לשמירה
            filename = get_next_file_name(token, target) if path_param else f"transcription_{api_id}.tts"
            upload_path = f"ivr2:{target}/{filename}"
            
            requests.get("https://www.call2all.co.il/ym/api/UploadTextFile", 
                         params={"token": token, "what": upload_path, "contents": final_text})
            
            # ניקוי קבצים
            for f in [flag_file, text_storage, k_counter_file]:
                if os.path.exists(f): os.remove(f)
            return "id_list_message=m-1452."

    # --- שלב תיקון: OK=2 ---
    if ok_val == "2":
        next_k = inc_k_count()
        set_state("RETRY")
        return f"read=m-1012=K{next_k},,record,{m_param},,no"

    # --- שלב עיבוד הקלטה (K) ---
    if received_k_path:
        down_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={token}&path=ivr2:{received_k_path}"
        res = requests.get(down_url)
        if res.status_code == 200:
            audio_tmp = os.path.join(TEMP_DIR, f"audio_{api_id}.wav")
            with open(audio_tmp, "wb") as f: f.write(res.content)
            text = recognize_speech(audio_tmp)
            if os.path.exists(audio_tmp): os.remove(audio_tmp)
            
            with open(text_storage, "w", encoding="utf-8") as f: f.write(text)
            set_state("WAITING_FOR_OK")
            
            return f"read=t-{text}.m-1078=OK,,1,1,,NO,,,,12,,,,,no"

    # --- שלב התחלה ראשוני ---
    if current_state is None:
        next_k = inc_k_count()
        set_state("START")
        return f"read=m-1012=K{next_k},,record,{m_param},,no"

    return "id_list_message=f-Error_General."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
