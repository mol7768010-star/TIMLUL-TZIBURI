@app.route("/transcribe", methods=["GET"])
def transcribe():
    token = request.args.get('token', '')
    k_path = request.args.get('K', '')
    api_id = request.args.get('ApiCallId', '')
    ok_val = request.args.get('OK', '')
    # ... יתר הפרמטרים ...

    flag_a = os.path.join(TEMP_DIR, f"flag_a_{api_id}.txt")
    flag_b = os.path.join(TEMP_DIR, f"flag_b_{api_id}.txt")
    text_storage = os.path.join(TEMP_DIR, f"trans_{api_id}.txt")

    # --- שינוי קריטי: אם הגיע K, זה אומר שהמשתמש סיים להקליט ---
    # אנחנו נתעלם מה-OK=2 הישן ונפנה לטיפול בהקלטה
    if k_path:
        # בדיקה אם אנחנו אחרי לחיצה על 2 (דגל A) או בסבב ראשון
        is_retry = os.path.exists(flag_a)
        
        # תמלול (הקוד של recognize_speech...)
        download_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={token}&path=ivr2:{k_path}"
        audio_res = requests.get(download_url)
        if audio_res.status_code == 200:
            temp_audio = os.path.join(TEMP_DIR, f"audio_{api_id}.wav")
            with open(temp_audio, "wb") as f: f.write(audio_res.content)
            text = recognize_speech(temp_audio)
            
            if "ERROR_SR" not in text:
                with open(text_storage, "w", encoding="utf-8") as f: f.write(text)
                
                # מעבר למצב המתנה לאישור (דגל B) וניקוי דגל A
                with open(flag_b, "w") as f: f.write("active")
                if os.path.exists(flag_a): os.remove(flag_a)
                
                # מחזירים למשתמש את התמלול לאישור
                return f"read=t-{text}.m-1078=OK,,1,1,,NO,,,,12,,,,,no"

    # --- רק אם לא הגיע K, נבדוק את ה-OK ---
    if ok_val == "2":
        # המשתמש ביקש להקליט מחדש - ננקה דגלים ונשים דגל A
        if os.path.exists(flag_b): os.remove(flag_b)
        with open(flag_a, "w") as f: f.write("active")
        return f"read=m-1012=K,,record,5,,no"

    if ok_val == "1" and os.path.exists(flag_b):
        # לוגיקת שמירה סופית (UploadTextFile...)
        # ... (כאן יבוא הקוד של העלאת הקובץ)
        return "id_list_message=m-1452."

    # ברירת מחדל: אם אין כלום, בקש הקלטה ראשונה
    return f"read=m-1012=K,,record,5,,no"
