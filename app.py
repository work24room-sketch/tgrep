from fastapi import FastAPI, UploadFile, File
from pydub import AudioSegment
import io

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Service is running"}

@app.post("/mix_audio/")
async def mix_audio(voice: UploadFile = File(...), music: UploadFile = File(...)):
    try:
        # Загружаем голос
        voice_bytes = await voice.read()
        voice_audio = AudioSegment.from_file(io.BytesIO(voice_bytes))

        # Загружаем музыку
        music_bytes = await music.read()
        music_audio = AudioSegment.from_file(io.BytesIO(music_bytes))

        # Обрезаем музыку по длине голоса
        music_audio = music_audio[:len(voice_audio)]

        # Уменьшаем громкость музыки (-10 dB)
        music_audio = music_audio - 10  

        # Делаем микс
        mixed = voice_audio.overlay(music_audio)

        # Сжимаем до mp3 (128 kbps)
        buf = io.BytesIO()
        mixed.export(buf, format="mp3", bitrate="128k")
        buf.seek(0)

        return {
            "status": "ok",
            "length_ms": len(mixed),
            "message": "Файл успешно обработан!"
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}
