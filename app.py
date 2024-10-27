from flask import Flask, request, jsonify, render_template, send_file, send_from_directory
from googletrans import Translator
import os
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, AudioFileClip
from werkzeug.utils import secure_filename
from pydub import AudioSegment
from pydub.silence import split_on_silence
import speech_recognition as sr
import mysql.connector
from spellchecker import SpellChecker

os.environ['IMAGEMAGICK_BINARY'] = r'C:\Program Files\ImageMagick-7.1.1-Q16-HDRI\magick.exe'  # Adjust this path accordingly

app = Flask(__name__)
#This file is edited by Keshav Gadhari, suraj gaikar, aditi kadam, swarangi jog
db_config = {
    'host': 'localhost',       # Your MySQL host
    'user': 'root',            # Your MySQL username
    'password': '',    # Your MySQL password
    'database': 'feedback_data'       # Your MySQL database name
}

translator = Translator()

UPLOAD_FOLDER = 'uploads'
PROCESSED_FOLDER = 'processed'

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

#Database code

@app.route('/submit', methods=['POST'])
def insert_data():
    data = request.get_json()
    name = data['name']
    age = data['age']
    email = data['email']
    contact = data['contact']
    msg = data['msg']

    # Insert data into MySQL
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        query = "INSERT INTO feedback (name,age,email,contact,msg) VALUES (%s, %s,%s, %s,%s)"
        cursor.execute(query, (name, age, email, contact, msg))
        conn.commit()

        return jsonify({'message': 'Feedback submitted'})
    except mysql.connector.Error as err:
        return jsonify({'message': f'Error: {err}'}), 500
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()


#Video-subtitle  generation

@app.route('/upload2', methods=['POST'])
def upload_video():
    if 'video' not in request.files:
        return jsonify({'success': False, 'error': 'No video file provided.'}), 400

    video = request.files['video']
    filename = secure_filename(video.filename)
    video_path = os.path.join(UPLOAD_FOLDER, filename)
    video.save(video_path)

    # Process the video to add Hindi subtitles
    processed_video_path = process_video(video_path, filename)

    return jsonify({
        'success': True,
        'video_url': f'/uploads/{filename}',
        'download_url': f'/processed/{os.path.basename(processed_video_path)}'
    })

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/processed/<filename>')
def processed_file(filename):
    return send_from_directory(PROCESSED_FOLDER, filename)

def process_video(video_path, filename):
    recognizer = sr.Recognizer()
    translator = Translator()

    # Load the video and extract the audio
    video = VideoFileClip(video_path)
    audio_path = os.path.join(UPLOAD_FOLDER, f"{os.path.splitext(filename)[0]}.wav")
    video.audio.write_audiofile(audio_path)

    # Load audio with pydub
    sound = AudioSegment.from_wav(audio_path)
    
    # Split the audio where silence is 700 ms or more and get chunks
    chunks = split_on_silence(sound, min_silence_len=300, silence_thresh=sound.dBFS-14, keep_silence=200)
    
    # Prepare to store subtitles
    subtitle_clips = []
    current_start_time = 0

    bottom_margin = 100
    video_height = video.size[1]

    for i, chunk in enumerate(chunks):
        chunk_filename = os.path.join(UPLOAD_FOLDER, f"chunk{i}.wav")
        chunk.export(chunk_filename, format="wav")

        with sr.AudioFile(chunk_filename) as source:
            audio_listened = recognizer.record(source)
            try:
                # Recognize the chunk
                english_text = recognizer.recognize_google(audio_listened)
                print(f"Chunk {i} - Recognized Text: {english_text}")  # Debug

                # Translate the recognized text to Hindi
                hindi_text = translator.translate(english_text, dest='hi').text
                print(f"Chunk {i} - Translated Text: {hindi_text}")  # Debug
                
                # Calculate duration of the chunk
                chunk_duration = len(chunk) / 1000.0

                # Create a subtitle clip
                subtitle = TextClip(english_text, fontsize=24, color='white', bg_color='black')
                subtitle = subtitle.set_position(('center', video_height - bottom_margin)).set_start(current_start_time).set_duration(chunk_duration)
                
                subtitle_clips.append(subtitle)

                # Update start time for the next chunk
                current_start_time += chunk_duration

            except sr.UnknownValueError:
                print(f"Chunk {i} - Could not understand audio")
            except sr.RequestError as e:
                print(f"Chunk {i} - Could not request results; {e}")
    
    if subtitle_clips:
        # Composite all subtitle clips with the original video
        final_video = CompositeVideoClip([video, *subtitle_clips])
        processed_video_path = os.path.join(PROCESSED_FOLDER, f"subtitled_{filename}")
        final_video.write_videofile(processed_video_path, codec='libx264', audio_codec='aac')
        print(f"Video with subtitles saved to: {processed_video_path}")  # Debug
    else:
        print("No subtitles were created.")  # Debug
        processed_video_path = video_path  # Just return the original video if no subtitles

    return processed_video_path



#Video-audio Mixer

@app.route('/upload', methods=['POST'])
def upload():
    video_file = request.files['video']
    audio_file = request.files['audio']

    video_path = os.path.join(app.config['UPLOAD_FOLDER'], video_file.filename)
    audio_path = os.path.join(app.config['UPLOAD_FOLDER'], audio_file.filename)
    
    video_file.save(video_path)
    audio_file.save(audio_path)

    # Combine video and audio
    video_clip = VideoFileClip(video_path)
    audio_clip = AudioFileClip(audio_path)

    final_clip = video_clip.set_audio(audio_clip)
    output_path = os.path.join(app.config['UPLOAD_FOLDER'], 'output.mp4')
    final_clip.write_videofile(output_path, codec="libx264")

    return send_file(output_path, as_attachment=True)

# Audio Book

@app.route('/translate', methods=['POST'])
def translate_text():
    data = request.get_json()
    text = data.get('text')
    target_lang = data.get('lang')

    if not text or not target_lang:
        return jsonify({'error': 'Invalid input'}), 400

    # Translate text
    translated = translator.translate(text, dest=target_lang)
    return jsonify({'translatedText': translated.text})

@app.route('/AudioBook')
def AudioBook():
    return app.send_static_file('AudioBook.html')

@app.route('/live')
def live():
    return app.send_static_file('Live_translator.html')

@app.route('/text')
def text():
    return app.send_static_file('text_translator.html')

@app.route('/blendm')
def blendm():
    return app.send_static_file('Blend_master.html')

@app.route('/craft')
def craft():
    return app.send_static_file('caption_crafting.html')

@app.route('/')
def index():
    return app.send_static_file('index.html')


if __name__ == '__main__':
    app.run(debug=True)
