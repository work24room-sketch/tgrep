from flask import Flask, request, send_file
from pydub import AudioSegment
import os
import uuid

app = Flask(__name__)

STATIC_PATH = "static"
OUT_PATH = os.path.join(STATIC_PATH, "out")
DEFAULT_MUSIC = os.path.join(STATIC_PATH, "default.mp3")

os.makedirs(OUT_PATH, exist_ok=True)

@app.route("/mix", methods=["POST"])
def mix_audio():
    """
    Ожидает два файла: voice (ogg/wav/mp3) и optional music (mp3)
    Возвращает готовый микс с плавными затуханиями
    """
    if 'voice' not in request.files:
        return "Загрузите голосовой файл (voice)", 400

    voice_file = request.files['voice']
    voice = AudioSegment.from_file(voice_file)

    # Фоновая музыка
    music_file = request.files.get('music')
    if music_file:
        music = AudioSegment.from_file(music_file)
    else:
        music = AudioSegment.from_file(DEFAULT_MUSIC)

    # Подгоняем длину музыки под голос + 5 секунд
    output_length = len(voice) + 5000
    if len(music) < output_length:
        music = music * ((output_length // len(music)) + 1)
    music = music[:output_length]

    # Плавные переходы
    music = music.fade_in(3000).fade_out(5000)

    # Приглушаем музыку на фоне голоса
    music_quiet = music - 8
    combined = music_quiet.overlay(voice, position=3000)

    # Сохраняем в уникальный файл
    filename = f"{uuid.uuid4().hex}.mp3"
    output_path = os.path.join(OUT_PATH, filename)
    combined.export(output_path, format="mp3")

    return send_file(output_path, as_attachment=True)
