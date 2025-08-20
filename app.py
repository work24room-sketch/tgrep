import os, shutil, uuid, subprocess
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse

app = FastAPI()

INPUT_DIR = "static/in"
OUTPUT_DIR = "static/out"
MUSIC_FILE = "static/default.mp3"

os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

@app.get("/")
def read_root():
    return {"message": "Service is running"}

@app.post("/mix")
async def mix_voice_with_music(
    voice: UploadFile = File(...), 
    music: UploadFile = File(None)
):
    # сохраняем голос
    voice_path = os.path.join(INPUT_DIR, f"{uuid.uuid4()}_{voice.filename}")
    with open(voice_path, "wb") as f:
        shutil.copyfileobj(voice.file, f)

    # сохраняем музыку или берём дефолт
    if music:
        music_path = os.path.join(INPUT_DIR, f"{uuid.uuid4()}_{music.filename}")
        with open(music_path, "wb") as f:
            shutil.copyfileobj(music.file, f)
    else:
        music_path = MUSIC_FILE

    # узнаём длительность голоса
    result = subprocess.run(
        ["ffprobe","-v","error","-show_entries","format=duration",
         "-of","default=noprint_wrappers=1:nokey=1", voice_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    voice_duration = float(result.stdout.strip())

    # финальный файл
    out_path = os.path.join(OUTPUT_DIR, f"{uuid.uuid4()}_mixed.mp3")

    # ffmpeg: обрезаем музыку и миксуем
    cmd = [
        "ffmpeg", "-y",
        "-i", music_path,
        "-i", voice_path,
        "-filter_complex",
        f"[0:a]atrim=0:{voice_duration},asetpts=PTS-STARTPTS[bg];"
        "[1:a]asetpts=PTS-STARTPTS[voice];"
        "[bg][voice]amix=inputs=2:dropout_transition=0",
        "-c:a", "libmp3lame",
        "-b:a", "128k",
        out_path
    ]
    subprocess.run(cmd, check=True)

    return FileResponse(out_path, media_type="audio/mpeg", filename="mixed.mp3")
