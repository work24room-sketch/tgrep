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

        # Задаём параметры
        delay_ms = 3000       # задержка голоса 3 сек
        post_music_ms = 5000  # музыка после голоса 5 сек

        # Делаем длину музыки = голос + задержка + пост-музыка
        target_length = delay_ms + len(voice_audio) + post_music_ms
        if len(music_audio) < target_length:
            loops = (target_length // len(music_audio)) + 1
            music_audio = (music_audio * loops)[:target_length]
        else:
            music_audio = music_audio[:target_length]

        # Уменьшаем громкость музыки
        music_audio = music_audio - 10  

        # Накладываем голос не с нуля, а с задержкой
        mixed = music_audio.overlay(voice_audio, position=delay_ms)

        # Экспортируем в mp3
        buf = io.BytesIO()
        mixed.export(buf, format="mp3", bitrate="128k")
        buf.seek(0)

        return {
            "status": "ok",
            "length_ms": len(mixed),
            "message": "Голос начнётся через 3 сек, музыка останется на фоне и продолжится на 5 сек дольше."
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}
