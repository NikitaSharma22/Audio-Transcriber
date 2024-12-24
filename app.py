from flask import Flask, request, jsonify, render_template, send_file
import os
import speech_recognition as sr
from pydub import AudioSegment
from docx import Document
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from io import BytesIO
import tempfile

app = Flask(__name__)

# Ensure temp directory exists
os.makedirs('temp', exist_ok=True)

@app.route('/')
def index():
    return render_template('transcribe.html')

@app.route('/transcribe', methods=['POST'])
def transcribe():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    audio_file = request.files['file']
    language = request.form.get('language', 'en')
    format_type = request.form.get('format', 'txt')  # Get requested format
    recognizer = sr.Recognizer()

    try:
        # Save the file temporarily
        file_path = os.path.join('temp', audio_file.filename)
        audio_file.save(file_path)

        # Convert the audio file to WAV if needed
        if not file_path.lower().endswith('.wav'):
            sound = AudioSegment.from_file(file_path)
            wav_path = os.path.splitext(file_path)[0] + '.wav'
            sound.export(wav_path, format="wav")
            os.remove(file_path)  # Remove original file
            file_path = wav_path

        # Transcribe the audio
        with sr.AudioFile(file_path) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language=language)

        # Clean up the WAV file
        os.remove(file_path)

        # Return the transcription in the requested format
        return jsonify({
            "transcription": text,
            "filename": os.path.splitext(audio_file.filename)[0]  # Return original filename without extension
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/download/<format_type>', methods=['POST'])
def download_file(format_type):
    try:
        data = request.json
        text = data.get('text')
        filename = data.get('filename', 'transcription')

        if format_type == 'txt':
            # Create text file
            buffer = BytesIO()
            buffer.write(text.encode('utf-8'))
            buffer.seek(0)
            return send_file(
                buffer,
                mimetype='text/plain',
                as_attachment=True,
                download_name=f"{filename}.txt"
            )

        elif format_type == 'docx':
            # Create DOCX file
            doc = Document()
            doc.add_paragraph(text)
            buffer = BytesIO()
            doc.save(buffer)
            buffer.seek(0)
            return send_file(
                buffer,
                mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                as_attachment=True,
                download_name=f"{filename}.docx"
            )

        elif format_type == 'pdf':
            # Create PDF file
            buffer = BytesIO()
            c = canvas.Canvas(buffer, pagesize=letter)
            width, height = letter
            
            # Split text into lines for PDF
            y = height - 40  # Start near top of page
            lines = []
            current_line = ""
            words = text.split()
            
            for word in words:
                test_line = current_line + " " + word if current_line else word
                if c.stringWidth(test_line, "Helvetica", 12) < width - 80:  # 40px margin on each side
                    current_line = test_line
                else:
                    lines.append(current_line)
                    current_line = word
            if current_line:
                lines.append(current_line)

            # Write lines to PDF
            for line in lines:
                if y < 40:  # If near bottom of page, start new page
                    c.showPage()
                    y = height - 40
                c.setFont("Helvetica", 12)
                c.drawString(40, y, line)
                y -= 20  # Move down for next line

            c.save()
            buffer.seek(0)
            return send_file(
                buffer,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=f"{filename}.pdf"
            )

        else:
            return jsonify({"error": "Invalid format"}), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)