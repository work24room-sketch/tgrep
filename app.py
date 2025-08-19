import os, json, tempfile, subprocess, uuid, requests
from fastapi import FastAPI, Body
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BASE_PUBLIC_URL = os.getenv("BASE_PUBLIC_URL", "")

app = FastAPI()
os.makedirs("static/out", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/health")
def health():
    return {"ok": True}

def tg_download_voice(file_id: str, token: str) -> str:
    r = requests.get(f"https://api.telegram.org/bot{token}/getFile", params={"file_id": file_id}, timeout=30)
    r.raise_for_status()
    file_path = r.json()["result"]["file_path"]
    url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".ogg")
    tmp.write(resp.content); tmp.close()
    return tmp.name

def http_download(url: str, suffix: str) -> str:
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(r.content); tmp.close()
    return tmp.name

def ffmpeg_mix(voice_path: str, music_path: str) -> str:
    out_id = uuid.uuid4().hex
    out_path = f"static/out/{out_id}.ogg"
    cmd = [
        "ffmpeg","-y",
        "-i", voice_path,
        "-stream_loop","-1","-i", music_path,
        "-filter_complex","[1:a]volume=0.2[a1];[0:a][a1]amix=inputs=2:duration=first:dropout_transition=3",
        "-c:a","libopus","-b:a","64k",
        out_path
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return out_path

def extract_chat_and_file_id(update: dict):
    for key in ("message","channel_post","edited_message"):
        node = update.get(key)
        if not node: 
            continue
        chat_id = (node.get("chat") or {}).get("id")
        if node.get("voice",{}).get("file_id"):
            return chat_id, node["voice"]["file_id"]
        if node.get("audio",{}).get("file_id"):
            return chat_id, node["audio"]["file_id"]
    return None, None

@app.post("/mix")
def mix(payload=Body(...)):
    tg_token = payload.get("telegram_token") or TELEGRAM_BOT_TOKEN
    if not tg_token:
        return JSONResponse({"ok": False, "error": "TELEGRAM_BOT_TOKEN not set"}, status_code=400)

    update = payload.get("webhook")
    if isinstance(update, str):
        update = json.loads(update)
    chat_id, file_id = extract_chat_and_file_id(update or {})
    if not file_id:
        return JSONResponse({"ok": False, "error": "voice/audio file_id not found in webhook"}, status_code=400)

    voice_path = tg_download_voice(file_id, tg_token)
    music_url = payload.get("bg_music_url") or f"{BASE_PUBLIC_URL}/static/default.mp3"
    music_path = http_download(music_url, ".mp3")

    out_path = ffmpeg_mix(voice_path, music_path)
    result_url = f"{BASE_PUBLIC_URL}/{out_path}"

    if payload.get("reply_mode") == "telegram":
        files = {"voice": open(out_path, "rb")}
        data = {"chat_id": chat_id} if chat_id else None
        r = requests.post(f"https://api.telegram.org/bot{tg_token}/sendVoice", data=data, files=files, timeout=60)
        return {"ok": r.ok, "sent_by": "bot", "result_url": result_url}

    return {"ok": True, "sent_by": "url", "result_url": result_url}
