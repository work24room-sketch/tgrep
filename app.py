from fastapi import FastAPI, UploadFile, File
from pydub import AudioSegment
import io

app = FastAPI()

@app.post("/mix_audio/")
async def mix_audio(voice: UploadFile = File(...), music: UploadFile = File(...)):
    try:
        # Загружаем голос
        voice_bytes = await voice.read()
        voice_audio = AudioSegment.from_file(io.BytesIO(voice_bytes))

        # Загружаем музыку
        music_bytes = await music.read()
        music_audio = AudioSegment.from_file(io.BytesIO(music_bytes))

        # Смещение голоса на 3 сек
        delay_ms = 3000
        voice_with_delay = AudioSegment.silent(duration=delay_ms) + voice_audio  

        # Длина музыки = длина голоса + 5 сек
        target_length = len(voice_with_delay) + 5000

        if len(music_audio) < target_length:
            # Зацикливаем если короче
            loops = (target_length // len(music_audio)) + 1
            music_audio = (music_audio * loops)[:target_length]
        else:
            # Обрезаем если длиннее
            music_audio = music_audio[:target_length]

        # Уменьшаем громкость музыки (-10 dB)
        music_audio = music_audio - 10  

        # Делаем микс (музыка + голос со смещением)
        mixed = music_audio.overlay(voice_with_delay)

        # Экспортируем в mp3
        buf = io.BytesIO()
        mixed.export(buf, format="mp3", bitrate="128k")
        buf.seek(0)

        return {
            "status": "ok",
            "length_ms": len(mixed),
            "message": "Голос начинается через 3 секунды, музыка продолжается 5 секунд после окончания."
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}
