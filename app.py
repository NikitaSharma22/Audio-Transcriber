# app.py
from flask import Flask, request, jsonify, render_template, send_file
import os
import speech_recognition as sr
from pydub import AudioSegment
from docx import Document
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from io import BytesIO
import tempfile
import re
import logging
from werkzeug.utils import secure_filename

# Initialize Flask application
app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
UPLOAD_FOLDER = 'temp'
ALLOWED_EXTENSIONS = {'wav', 'mp3', 'ogg', 'flac', 'm4a'}

# Ensure temp directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    """Check if the uploaded file has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def clean_filename(filename):
    """Generate a secure filename and ensure no spaces."""
    return secure_filename(filename).replace(' ', '_')

@app.route('/')
def index():
    """Render the main page."""
    return render_template('transcribe.html')

@app.route('/transcribe', methods=['POST'])
def transcribe():
    """Handle audio file upload and transcription."""
    try:
        # Validate file presence
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
        
        audio_file = request.files['file']
        if not audio_file or not audio_file.filename:
            return jsonify({"error": "No file selected"}), 400

        # Validate file type
        if not allowed_file(audio_file.filename):
            return jsonify({"error": f"File type not allowed. Supported types: {', '.join(ALLOWED_EXTENSIONS)}"}), 400

        # Get language selection (default to English if not specified)
        language = request.form.get('language', 'en')
        
        # Initialize speech recognizer
        recognizer = sr.Recognizer()
        
        # Create a secure filename and save path
        filename = clean_filename(audio_file.filename)
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        wav_path = os.path.join(UPLOAD_FOLDER, f"{os.path.splitext(filename)[0]}.wav")

        try:
            # Save uploaded file
            audio_file.save(file_path)
            
            # Convert to WAV if necessary
            if not file_path.lower().endswith('.wav'):
                sound = AudioSegment.from_file(file_path)
                sound.export(wav_path, format="wav")
                os.remove(file_path)  # Remove original file
                file_path = wav_path

            # Perform transcription
            with sr.AudioFile(file_path) as source:
                audio_data = recognizer.record(source)
                text = recognizer.recognize_google(audio_data, language=language)

            # Enhance text with punctuation and formatting
            text = enhance_text(text)

            return jsonify({
                "transcription": text,
                "filename": os.path.splitext(filename)[0]
            })

        finally:
            # Clean up temporary files
            for temp_file in [file_path, wav_path]:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except Exception as e:
                    logger.error(f"Error cleaning up file {temp_file}: {str(e)}")

    except Exception as e:
        logger.error(f"Transcription error: {str(e)}")
        return jsonify({"error": "An error occurred during transcription. Please try again."}), 500

@app.route('/download/<format_type>', methods=['POST'])
def download_file(format_type):
    """Handle file download in various formats."""
    try:
        data = request.json
        if not data or 'text' not in data:
            return jsonify({"error": "No text provided"}), 400

        text = data['text']
        filename = clean_filename(data.get('filename', 'transcription'))

        if format_type == 'txt':
            return create_txt_file(text, filename)
        elif format_type == 'docx':
            return create_docx_file(text, filename)
        elif format_type == 'pdf':
            return create_pdf_file(text, filename)
        else:
            return jsonify({"error": "Invalid format"}), 400

    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        return jsonify({"error": "An error occurred during file creation"}), 500

def create_txt_file(text, filename):
    """Create and return a text file."""
    buffer = BytesIO()
    buffer.write(text.encode('utf-8'))
    buffer.seek(0)
    return send_file(
        buffer,
        mimetype='text/plain',
        as_attachment=True,
        download_name=f"{filename}.txt"
    )

def create_docx_file(text, filename):
    """Create and return a DOCX file."""
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

def create_pdf_file(text, filename):
    """Create and return a PDF file with proper text wrapping."""
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # PDF formatting settings
    margin = 40
    font_size = 12
    line_height = 20
    max_width = width - (2 * margin)
    y = height - margin
    
    # Format text into lines
    lines = format_text_for_pdf(text, c, "Helvetica", font_size, max_width)
    
    # Write lines to PDF
    for line in lines:
        if y < margin:  # Start new page if near bottom
            c.showPage()
            y = height - margin
        c.setFont("Helvetica", font_size)
        c.drawString(margin, y, line)
        y -= line_height

    c.save()
    buffer.seek(0)
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"{filename}.pdf"
    )

def format_text_for_pdf(text, canvas, font_name, font_size, max_width):
    """Format text into lines that fit within PDF width."""
    lines = []
    current_line = []
    words = text.split()
    
    for word in words:
        current_line.append(word)
        line_text = ' '.join(current_line)
        if canvas.stringWidth(line_text, font_name, font_size) > max_width:
            current_line.pop()
            lines.append(' '.join(current_line))
            current_line = [word]
    
    if current_line:
        lines.append(' '.join(current_line))
    
    return lines

def enhance_text(text):
    """Enhance text with proper punctuation and formatting."""
    # List of sentence-ending words that should have periods
    sentence_enders = r'\b(?:ok|okay|right|alright|sure|yeah|yes|no|thanks|thank you|please|sorry|excuse me)\b'
    
    # Add periods after sentence-ending words
    text = re.sub(f"({sentence_enders})", r"\1.", text, flags=re.IGNORECASE)
    
    # Add commas before conjunctions
    text = re.sub(r'\s+(and|but|or|so|yet|for|nor)\s+', r', \1 ', text, flags=re.IGNORECASE)
    
    # Add periods after common pronouns when followed by capital letters
    text = re.sub(r'(\b(?:he|she|it|they|we|you|I)\b)(?=\s+[A-Z])', r'\1.', text)
    
    # Ensure first letter is capitalized
    text = text[0].upper() + text[1:] if text else text
    
    # Ensure text ends with a period
    if text and not text.rstrip().endswith(('.', '!', '?')):
        text = text.rstrip() + '.'
    
    # Fix multiple periods
    text = re.sub(r'\.+', '.', text)
    
    # Fix spaces around punctuation
    text = re.sub(r'\s+([.,!?])', r'\1', text)
    text = re.sub(r'([.,!?])(?=[A-Za-z])', r'\1 ', text)
    
    return text

if __name__ == '__main__':
    app.run(debug=True)     