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
    # שליפת פרמטרים בסיסיים
    token = request.args.get('token', '')
    token_z = request.args.get('token_z', '')
    url_u = request.args.get('urlu', '')
    z_param = request.args.get('Z')
    m_param = request.args.get('M', '5') # פרמטר M
    t_param = request.args.get('T', '') # פרמטר T החדש שביקשת
    
    k_path = request.args.get('K', '')
    n_param = request.args.get('N', '')
    api_id = request.args.get('ApiCallId', '')
    ok_val = request.args.get('OK', '')
    log_enabled = request.args.get('LOG') == "1"

    if not api_id:
        return "Missing ApiCallId", 400

    text_storage = os.path.join(TEMP_DIR, f"trans_{api_id}.txt")
    
    # --- טיפול בפרמטר Z ---
    if z_param:
        try:
            # 1. קבלת פרטי השלוחה
            stats_url = "https://www.call2all.co.il/ym/api/GetIVR2DirStats"
            stats_res = requests.get(stats_url, params={"token": token, "path": f"ivr2:{z_param}"}).json()
            
            if stats_res.get("responseStatus") == "OK" and "maxFile" in stats_res:
                file_to_download = stats_res["maxFile"]["path"]
                
                # 2. הורדת הקובץ
                download_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={token}&path=ivr2:{file_to_download}"
                audio_data = requests.get(download_url).content
                temp_audio = os.path.join(TEMP_DIR, f"audio_z_{api_id}.wav")
                
                with open(temp_audio, "wb") as f:
                    f.write(audio_data)
                
                # 3. תמלול
                transcribed_text = recognize_speech(temp_audio)
                if os.path.exists(temp_audio): os.remove(temp_audio)

                # 4. שליחה ל-Google Chat
                chat_url = f"https://chat.googleapis.com/v1/spaces/AAQAWjjfDoU/messages?key=AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI&token={token_z}"
                requests.post(chat_url, json={"text": transcribed_text})

                # 5. שליחה לכתובת urlu עם M ו-TI (התוספת החדשה)
                if url_u:
                    final_params = {
                        "text": transcribed_text,
                        "file": file_to_download,
                        "M": m_param,
                        "T": t_param
                    }
                    requests.get(url_u, params=final_params)

                return f"id_list_message=t-בוצע בהצלחה לקובץ {file_to_download}."
            else:
                return "id_list_message=f-No_Files_Found."
        except Exception as e:
            return f"Error_Z: {str(e)}"

    # --- שאר הקוד המקורי ללא שינוי ---
    # (כאן מופיע הקוד שטיפל ב-OK=1 ובתמלול רגיל של K כפי שהיה קודם)
    ignore_flag = os.path.join(TEMP_DIR, f"ignore_{api_id}.txt")
    if os.path.exists(ignore_flag):
        os.remove(ignore_flag)
        ok_val = None

    if ok_val == "1":
        if os.path.exists(text_storage):
            with open(text_storage, "r", encoding="utf-8") as f:
                final_text = f.read()
            orig_filename = k_path.split('/')[-1] if k_path else "file.wav"
            upload_path = f"ivr2:{n_param}/{orig_filename.replace('.wav', '.tts')}"
            upload_url = "https://www.call2all.co.il/ym/api/UploadTextFile"
            params = {"token": token, "what": upload_path, "contents": final_text}
            try:
                response = requests.get(upload_url, params=params)
                if response.status_code == 200:
                    os.remove(text_storage)
                    return "id_list_message=m-1452."
                return f"id_list_message=f-Server_Error_{response.status_code}."
            except:
                return "id_list_message=f-Connection_Error."
        return "id_list_message=f-No_Stored_Text."

    elif ok_val == "2":
        with open(ignore_flag, "w") as f: f.write("1")
        return f"read=m-1012=K,,record,{m_param},,no"

    if not k_path:
        return f"read=m-1012=K,,record,{m_param},,no"

    try:
        audio_response = requests.get(f"https://www.call2all.co.il/ym/api/DownloadFile?token={token}&path=ivr2:{k_path}")
        if audio_response.status_code == 200:
            temp_audio = os.path.join(TEMP_DIR, f"audio_{api_id}.wav")
            with open(temp_audio, "wb") as f: f.write(audio_response.content)
            text = recognize_speech(temp_audio)
            if os.path.exists(temp_audio): os.remove(temp_audio)
            with open(text_storage, "w", encoding="utf-8") as f: f.write(text)
            return f"read=t-{text}.m-1078=OK,,1,1,,NO,,,,12,,,,,no"
        return "id_list_message=f-Download_Failed."
    except Exception as e:
        return f"Error: {str(e)}"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
