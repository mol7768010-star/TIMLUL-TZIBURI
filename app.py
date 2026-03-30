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
    """
    פונקציה שבודקת מהו הקובץ הכי גבוה בשלוחה ומחזירה את המספר הבא בתור עם סיומת .tts
    """
    url = "https://www.call2all.co.il/ym/api/GetIVR2DirStats"
    params = {"token": token, "path": f"ivr2:{folder_path}"}
    try:
        response = requests.get(url, params=params)
        data = response.json()
        if data.get("responseStatus") == "OK" and data.get("maxFile", {}).get("exists"):
            max_name = data["maxFile"]["name"]  # למשל "386.wav"
            name_without_ext = max_name.split('.')[0]
            if name_without_ext.isdigit():
                next_number = int(name_without_ext) + 1
                return f"{next_number:03d}.tts" # שומר על פורמט 3 ספרות אם תרצה, או פשוט str
        return "000.tts" # ברירת מחדל אם השלוחה ריקה
    except Exception:
        return "error_name.tts"

@app.route("/transcribe", methods=["GET"])
def transcribe():
    # שליפת פרמטרים
    token = request.args.get('token', '')
    k_path = request.args.get('K', '')
    m_param = request.args.get('M', '5')
    n_param = request.args.get('N', '')
    path_param = request.args.get('path', '') # הפרמטר החדש
    api_id = request.args.get('ApiCallId', '')
    ok_val = request.args.get('OK', '')
    log_enabled = request.args.get('LOG') == "1"

    logs = []
    
    if not api_id:
        return "Missing ApiCallId", 400

    text_storage = os.path.join(TEMP_DIR, f"trans_{api_id}.txt")
    ignore_flag = os.path.join(TEMP_DIR, f"ignore_{api_id}.txt")

    if os.path.exists(ignore_flag):
        os.remove(ignore_flag)
        ok_val = None

    # --- שלב 2: אישור המשתמש ושמירה סופית (OK=1) ---
    if ok_val == "1":
        if os.path.exists(text_storage):
            with open(text_storage, "r", encoding="utf-8") as f:
                final_text = f.read()
            
            # קביעת יעד השמירה
            if path_param:
                # אם נשלח path, מחפשים את המספר הבא בשלוחה
                target_folder = path_param
                filename = get_next_file_name(token, target_folder)
                upload_path = f"ivr2:{target_folder}/{filename}"
            else:
                # אם נשלח N (או כברירת מחדל), עובדים לפי הלוגיקה הישנה
                orig_filename = k_path.split('/')[-1] if k_path else "file.wav"
                upload_path = f"ivr2:{n_param}/{orig_filename.replace('.wav', '.tts')}"
            
            upload_url = "https://www.call2all.co.il/ym/api/UploadTextFile"
            params = {
                "token": token,
                "what": upload_path,
                "contents": final_text
            }
            
            if log_enabled: logs.append(f"Target path: {upload_path}")
            
            try:
                response = requests.get(upload_url, params=params)
                if response.status_code == 200:
                    os.remove(text_storage)
                    res = "id_list_message=m-1452." # הודעת סיום מוצלחת
                else:
                    res = f"id_list_message=f-Server_Error_{response.status_code}."
            except Exception as e:
                res = "id_list_message=f-Connection_Error."
        else:
            res = "id_list_message=f-No_Stored_Text."

        return "<br>".join(logs) if log_enabled else res

    # --- טיפול ב-OK=2 (הקלטה מחדש) ---
    elif ok_val == "2":
        with open(ignore_flag, "w") as f: f.write("1")
        return f"read=m-1012=K,,record,{m_param},,no"

    # --- שלב 1: הקלטה או תמלול ---
    if not k_path:
        return f"read=m-1012=K,,record,{m_param},,no"

    download_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={token}&path=ivr2:{k_path}"
    
    try:
        audio_response = requests.get(download_url)
        if audio_response.status_code == 200:
            temp_audio = os.path.join(TEMP_DIR, f"audio_{api_id}.wav")
            with open(temp_audio, "wb") as f:
                f.write(audio_response.content)
            
            text = recognize_speech(temp_audio)
            if os.path.exists(temp_audio): os.remove(temp_audio)
            
            if "ERROR_SR" in text:
                return "id_list_message=f-Error_Transcription."
            
            with open(text_storage, "w", encoding="utf-8") as f:
                f.write(text)
            
            # החזרת הפלט למשתמש לאישור (OK=1 לאישור, OK=2 להקלטה מחדש)
            return f"read=t-{text}.m-1078=OK,,1,1,,NO,,,,12,,,,,no"
        else:
            return "id_list_message=f-Download_Failed."
    except Exception as e:
        return f"Error: {str(e)}"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
