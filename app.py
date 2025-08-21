import os, json, tempfile, subprocess, uuid, requests, shutil
from fastapi import FastAPI, Body, File, UploadFile
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# -------- Конфиг из переменных окружения --------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    logging.error("Критическая ошибка: переменная окружения TELEGRAM_BOT_TOKEN не задана!")
    # В продакшене лучше использовать raise, но для Render подойдет и logging
    # raise ValueError("TELEGRAM_BOT_TOKEN not set in environment variables")
BASE_PUBLIC_URL    = os.getenv("BASE_PUBLIC_URL", "https://tgrep.onrender.com")  # например: https://tgrep.onrender.com

# -------- Инициализация --------
app = FastAPI()
STATIC_DIR = "static"
IN_DIR     = os.path.join(STATIC_DIR, "in")
OUT_DIR    = os.path.join(STATIC_DIR, "out")
DEFAULT_MUSIC = os.path.join(STATIC_DIR, "default.mp3")

os.makedirs(IN_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def root():
    return {"message": "Service is running"}

@app.get("/health")
def health():
    return {"ok": True}

# -------- Утилиты --------
def _ffprobe_duration_sec(path: str) -> float:
    """
    Возвращает длительность файла в секундах (float).
    Пытаемся сначала stream=duration, затем format=duration.
    """
    for args in (
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=duration", "-of", "default=nk=1:nw=1", path],
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nk=1:nw=1", path],
    ):
        p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        val = p.stdout.decode().strip()
        try:
            dur = float(val)
            if dur > 0:
                return dur
        except:
            pass
    # запасной вариант
    return 0.0

def tg_download_file(file_id: str, token: str, suffix: str = ".ogg") -> str:
    r = requests.get(f"https://api.telegram.org/bot{token}/getFile",
                     params={"file_id": file_id}, timeout=30)
    r.raise_for_status()
    file_path = r.json()["result"]["file_path"]
    url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(resp.content); tmp.close()
    return tmp.name

def http_download(url: str, suffix: str) -> str:
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(r.content); tmp.close()
    return tmp.name

def extract_chat_and_file_id(update):
    """
    Извлекает chat_id и file_id из update.
    Теперь принимает как dict, так и str (автоматически конвертирует).
    """
    # Если update - строка, пытаемся распарсить её как JSON
    if isinstance(update, str):
        try:
            update = json.loads(update)
        except json.JSONDecodeError:
            return None, None, None
    
    # Если update - bytes, декодируем в строку и парсим
    if isinstance(update, bytes):
        try:
            update = json.loads(update.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None, None, None
    
    # Теперь работаем с dict
    if not isinstance(update, dict):
        return None, None, None

    for key in ("message", "channel_post", "edited_message"):
        node = update.get(key)
        if not node:
            continue
        chat_id = (node.get("chat") or {}).get("id")
        if node.get("voice", {}).get("file_id"):
            return chat_id, node["voice"]["file_id"], "voice"
        if node.get("audio", {}).get("file_id"):
            return chat_id, node["audio"]["file_id"], "audio"
    return None, None, None

def ffmpeg_mix(
    voice_path: str,
    music_path: str,
    delay_ms: int = 3000,      # задержка старта голоса
    post_ms: int = 5000,       # хвост музыки после окончания голоса
    bg_db: float = -10.0,      # ослабление музыки в dB
    out_codec: str = "libopus",
    out_bitrate: str = "64k",
) -> str:
    """
    Микс с гарантированной обрезкой/зацикливанием музыки и задержкой голоса.
    Выход: OGG (Opus) для совместимости с Telegram sendVoice.
    """
    # 1) длительность голоса (сек)
    vdur = _ffprobe_duration_sec(voice_path)
    if vdur <= 0:
        # если не удалось — даём минимально разумную длину
        vdur = 3.0
    # 2) итоговая длительность (сек). Музыка = delay + voice + post
    target_len_sec = (delay_ms / 1000.0) + vdur + (post_ms / 1000.0)

    # 3) Выходной файл
    out_id = uuid.uuid4().hex
    out_path = os.path.join(OUT_DIR, f"{out_id}.ogg")

    # 4) Сборка фильтров:
    #   - музыка: уменьшаем громкость (в dB: volume=10^(db/20)), но в FFmpeg проще сразу dB:
    #             фильтр volume принимает коэффициент, а не dB. Для dB используем volume=<coef>
    #             coef = 10^(db/20). Для -10 dB это ~0.316.
    import math
    bg_coef = str(round(math.pow(10.0, bg_db / 20.0), 6))

    #   - голос: adelay=delay_ms на каждый канал. Для стерео "X|X".
    #            если будет моно — FFmpeg просто возьмёт первый.
    adelay_arg = f"{delay_ms}|{delay_ms}"

    # ВАЖНО: используем -stream_loop -1 на музыке и -t <target> на всём выходе,
    # чтобы музыка гарантированно покрыла нужную длину и обрезалась ровно.
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", music_path,  # зацикливаем музыку при необходимости
        "-i", voice_path,                        # голос
        "-t", str(target_len_sec),               # итоговая длительность ролика
        "-filter_complex",
        f"[0:a]volume={bg_coef}[bg];"
        f"[1:a]adelay={adelay_arg}[voice_d];"
        f"[bg][voice_d]amix=inputs=2:dropout_transition=0,aresample=48000[aout]",
        "-map", "[aout]",
        "-c:a", out_codec, "-b:a", out_bitrate,
        out_path
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return out_path

# -------- 1) Ручной аплоад для тестов (Postman/curl) --------
@app.post("/mix-upload")
async def mix_upload(
    voice: UploadFile = File(...),
    music: UploadFile = File(None),
    delay_ms: int = 3000,
    post_ms: int = 5000,
    bg_db: float = -10.0
):
    # сохраняем входы
    v_path = os.path.join(IN_DIR, f"{uuid.uuid4().hex}_{voice.filename}")
    with open(v_path, "wb") as f:
        shutil.copyfileobj(voice.file, f)

    if music is not None:
        m_path = os.path.join(IN_DIR, f"{uuid.uuid4().hex}_{music.filename}")
        with open(m_path, "wb") as f:
            shutil.copyfileobj(music.file, f)
    else:
        m_path = DEFAULT_MUSIC

    out_path = ffmpeg_mix(v_path, m_path, delay_ms=delay_ms, post_ms=post_ms, bg_db=bg_db)
    return FileResponse(out_path, media_type="audio/ogg", filename="mixed.ogg")

# -------- 2) Telegram webhook JSON (SaleBot/интеграция) --------
@app.post("/mix")
def mix(payload: dict = Body(...)):  # Явно указываем тип dict
    tg_token = payload.get("telegram_token") or TELEGRAM_BOT_TOKEN
    if not tg_token:
        return JSONResponse({"ok": False, "error": "TELEGRAM_BOT_TOKEN not set"}, status_code=400)
    # Параметры микса (можно присылать из SaleBot)
    delay_ms = int(payload.get("delay_ms", 3000))
    post_ms  = int(payload.get("post_ms", 5000))
    bg_db    = float(payload.get("bg_db", -10.0))

    # Разбор апдейта
    update = payload.get("webhook")
    if isinstance(update, str):
        update = json.loads(update)
    chat_id, file_id, kind = extract_chat_and_file_id(update or {})
    if not file_id:
        return JSONResponse({"ok": False, "error": "voice/audio file_id not found in webhook"}, status_code=400)

    # Скачиваем голос
    suffix = ".ogg" if kind == "voice" else ".mp3"
    voice_path = tg_download_file(file_id, tg_token, suffix=suffix)

    # Музыка: из payload или дефолт
    music_url = payload.get("bg_music_url") or (BASE_PUBLIC_URL + "/static/default.mp3")
    music_path = http_download(music_url, ".mp3")

    # Микс
    out_path = ffmpeg_mix(voice_path, music_path, delay_ms=delay_ms, post_ms=post_ms, bg_db=bg_db)
    result_url = (BASE_PUBLIC_URL.rstrip("/") + "/" + out_path)

    # Отправка назад в Telegram (если указано)
    if payload.get("reply_mode") == "telegram":
        with open(out_path, "rb") as f:
            files = {"voice": f}  # .ogg opus — совместимо с sendVoice
            data = {"chat_id": chat_id} if chat_id else None
            r = requests.post(f"https://api.telegram.org/bot{tg_token}/sendVoice",
                              data=data, files=files, timeout=120)
        return {"ok": r.ok, "sent_by": "bot", "result_url": result_url}

    # Иначе — просто ссылка
    return {"ok": True, "sent_by": "url", "result_url": result_url}
