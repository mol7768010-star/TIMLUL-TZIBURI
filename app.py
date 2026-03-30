@app.route("/transcribe", methods=["GET"])
def transcribe():
    token = request.args.get('token', '')
    folder_path = request.args.get('path', '')  # במקום K
    api_id = request.args.get('ApiCallId', '')
    forward_url = request.args.get('URL', '')
    token_g = request.args.get('token_g', '')

    if not api_id:
        return "Missing ApiCallId", 400

    # --- שלב 1: קבלת הקובץ האחרון ---
    list_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={token}&path=ivr2:{folder_path}"

    try:
        resp = requests.get(list_url)
        data = resp.json()

        if data.get("responseStatus") != "OK":
            return "id_list_message=f-List_Error."

        max_file = data.get("maxFile", {})
        file_path = max_file.get("path")

        if not file_path:
            return "id_list_message=f-No_File."

    except Exception as e:
        return f"Error listing files: {str(e)}"

    # --- שלב 2: הורדת הקובץ ---
    download_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={token}&path=ivr2:{file_path}"

    try:
        audio_response = requests.get(download_url)

        if audio_response.status_code != 200:
            return "id_list_message=f-Download_Failed."

        temp_audio = os.path.join(TEMP_DIR, f"audio_{api_id}.wav")

        with open(temp_audio, "wb") as f:
            f.write(audio_response.content)

    except Exception as e:
        return f"Download error: {str(e)}"

    # --- שלב 3: תמלול ---
    text = recognize_speech(temp_audio)

    if os.path.exists(temp_audio):
        os.remove(temp_audio)

    if "ERROR_SR" in text:
        return "id_list_message=f-Error_Transcription."

    # --- שלב 4: שליחה ל-Google Chat ---
    chat_url = f"https://chat.googleapis.com/v1/spaces/AAQAWjjfDoU/messages?key=AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI&token={token_g}"

    try:
        requests.post(chat_url, json={"text": text})
    except Exception as e:
        return f"Chat error: {str(e)}"

    # --- שלב 5: שליחת פרמטרים לא מנוצלים ---
    if forward_url:
        unused_params = request.args.to_dict()

        # אפשר להסיר מה שכבר השתמשנו
        for used in ["path", "token_g"]:
            unused_params.pop(used, None)

        try:
            requests.get(forward_url, params=unused_params)
        except Exception as e:
            return f"Forward error: {str(e)}"

    return "id_list_message=m-1452."
