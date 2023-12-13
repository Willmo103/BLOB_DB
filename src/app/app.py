from flask import Flask, request, send_file, render_template, redirect, url_for
import psycopg2, io
from os import getenv
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
## set the jinja template config

def get_db_connection():
    return psycopg2.connect(getenv('DATABASE_URL'))

@app.route('/')
def index():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, filename FROM scripts')
    files = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('index.html', files=files)

@app.route('/', methods=['POST'])
def upload_file():
    file = request.files['file']
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO scripts (filename, data, mimetype) VALUES (%s, %s, %s)',
                (file.filename, file.read(), file.mimetype))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('index'))

@app.route('/download/<int:id>')
def download_file(id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT filename, data, mimetype FROM scripts WHERE id = %s', (id,))
    file = cur.fetchone()
    cur.close()
    conn.close()
    return send_file(io.BytesIO(file[1]), mimetype=file[2], as_attachment=True, attachment_filename=file[0])

if __name__ == '__main__':
    app.run(debug=True)
