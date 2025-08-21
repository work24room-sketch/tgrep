from flask import Flask, request, send_from_directory, jsonify
import os
from pydub import AudioSegment
import uuid

app = Flask(__name__)

UPLOAD_FOLDER = "static/out"
DEFAULT_MUSIC = "static/default.mp3"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route("/mix", methods=["POST"])
def mix_audio():
    if "voice" not in request.files:
        return jsonify({"error": "No voice file"}), 400

    voice_file = request.files["voice"]
    voice_path = os.path.join(UPLOAD_FOLDER, f"voice_{uuid.uuid4()}.ogg")
    voice_file.save(voice_path)

    # Загружаем голос и фоновую музыку
    voice = AudioSegment.from_file(voice_path, format="ogg")
    music = AudioSegment.from_file(DEFAULT_MUSIC, format="mp3")

    # Делаем фон тише
    music = music - 10

    # Укорачиваем фон до длины голоса
    music = music[:len(voice)]

    # Смешиваем
    mixed = voice.overlay(music)

    # Сохраняем результат
    out_filename = f"mix_{uuid.uuid4()}.mp3"
    out_path = os.path.join(UPLOAD_FOLDER, out_filename)
    mixed.export(out_path, format="mp3")

    # Возвращаем ссылку
    return jsonify({
        "url": f"https://{request.host}/static/out/{out_filename}"
    })

@app.route("/static/out/<filename>")
def serve_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)
