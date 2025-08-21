from flask import Flask, request, send_file
from pydub import AudioSegment
import os

app = Flask(__name__)

@app.route('/mix', methods=['POST'])
def mix_audio():
    """
    Ожидает два файла: voice (wav/mp3) и music (mp3)
    Возвращает готовый микс с плавными затуханиями.
    """
    if 'voice' not in request.files or 'music' not in request.files:
        return "Загрузите voice и music файлы", 400

    # === 1. Загружаем файлы ===
    voice_file = request.files['voice']
    music_file = request.files['music']

    voice = AudioSegment.from_file(voice_file)
    music = AudioSegment.from_file(music_file)

    # === 2. Настраиваем длительность ===
    # Музыка должна быть длиннее голоса на 5 секунд
    output_length = len(voice) + 5000

    if len(music) < output_length:
        # если музыка короткая, повторяем
        music = music * ((output_length // len(music)) + 1)

    # обрезаем под длину
    music = music[:output_length]

    # === 3. Плавные переходы ===
    music = music.fade_in(3000).fade_out(5000)  # fade-in 3с, fade-out 5с

    # === 4. Приглушаем музыку во время речи ===
    music_quiet = music - 8  # тише на 8 dB
    combined = music_quiet.overlay(voice, position=3000)  # голос через 3 сек

    # === 5. Сохраняем результат ===
    output_path = "final_output.mp3"
    combined.export(output_path, format="mp3")

    return send_file(output_path, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
