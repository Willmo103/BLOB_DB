import io
from os import getenv
import psycopg2
from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, send_file, url_for

load_dotenv()

app = Flask(__name__, template_folder="../templates")


class Script:
    def __init__(self, filename, data, mimetype):
        self.filename = filename
        self.data = data
        self.mimetype = mimetype

    @staticmethod
    def create_table():
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            DROP TABLE IF EXISTS public.scripts;
            CREATE TABLE IF NOT EXISTS public.scripts (
                id SERIAL PRIMARY KEY,
                filename VARCHAR(255),
                data BYTEA,
                mimetype VARCHAR(50),
                encrypted BOOLEAN DEFAULT FALSE,
                encrypt_key BYTEA,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        cur.close()
        conn.close()


class EncryptionHandler:
    def __init__(self, key):
        self.key = key


def get_db_connection():
    return psycopg2.connect(getenv("DATABASE_URL"))


@app.route("/")
def index():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, filename FROM scripts")
    files = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("index.html", files=files)


@app.route("/", methods=["POST"])
def upload_file():
    file = request.files["file"]
    if request.form.get("encrypt") is not None:
        # Encrypt the file if the encrypt checkbox is checked
        key = request.form["key"]
        # Use the key to encrypt the file
        # encrypted_file = encrypt_file(file, key)
        encrypted_file = file
        # Save the encrypted file to the database
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO scripts (filename, data, mimetype) VALUES (%s, %s, %s)",
        (file.filename, encrypted_file.read(), file.mimetype),
    )
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for("index"))


@app.route("/download/<int:id>")
def download_file(id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT filename, data, mimetype FROM scripts WHERE id = %s", (id,))
    file = cur.fetchone()
    cur.close()
    conn.close()
    if file:
        return send_file(
            io.BytesIO(file[1]),
            mimetype=file[2],
            as_attachment=True,
            download_name=file[0],
        )
    else:
        # Handle the case where the file is not found
        return "File not found", 404


@app.route('/delete/<int:id>', methods=['POST'])
def delete_file(id):
    conn = get_db_connection()
    cur = conn.cursor()
    # Delete the file entry from the database
    cur.execute('DELETE FROM scripts WHERE id = %s', (id,))
    conn.commit()
    cur.close()
    conn.close()
    # Redirect back to the homepage after deletion
    return redirect(url_for('index'))


if __name__ == "__main__":
    Script.create_table()  # Create the table before running the app
    app.run(debug=True)
