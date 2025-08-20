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

        # Добавляем 3 секунды тишины перед голосом
        silence = AudioSegment.silent(duration=3000)
        voice_audio = silence + voice_audio  

        # Делаем так, чтобы музыка играла +5 секунд после конца голоса
        target_length = len(voice_audio) + 5000
        music_audio = music_audio[:target_length]  # если музыка длиннее — обрезаем
        if len(music_audio) < target_length:  
            # если музыка короче — зациклим её
            loops = (target_length // len(music_audio)) + 1
            music_audio = (music_audio * loops)[:target_length]

        # Уменьшаем громкость музыки (-10 dB)
        music_audio = music_audio - 10  

        # Делаем микс
        mixed = music_audio.overlay(voice_audio)

        # Сжимаем до mp3 (128 kbps)
        buf = io.BytesIO()
        mixed.export(buf, format="mp3", bitrate="128k")
        buf.seek(0)

        return {
            "status": "ok",
            "length_ms": len(mixed),
            "message": "Файл успешно обработан! Голос начинается через 3 сек, музыка продолжается +5 сек."
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}
