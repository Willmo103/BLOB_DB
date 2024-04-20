import os
from cryptography.hazmat.primitives import padding
import hashlib
import io
from os import getenv
import psycopg2
from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, send_file, url_for
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import zipfile
import tempfile

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

    def encrypt_file(self, file_data):
        # Hash the plaintext key
        key = self.key.strip()
        hashed_key = hashlib.sha256(key.encode()).digest()

        # Create a temporary ZIP archive containing the file
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            with zipfile.ZipFile(temp_file.name, 'w') as zip_file:
                zip_file.writestr('file', file_data)

            # Read the ZIP archive data
            with open(temp_file.name, 'rb') as f:
                zip_data = f.read()

        # Remove the temporary ZIP file
        os.unlink(temp_file.name)

        # Create a cipher object using AES-256 in CBC mode
        backend = default_backend()
        cipher = Cipher(algorithms.AES(hashed_key), modes.CBC(
            hashed_key[:16]), backend=backend)
        encryptor = cipher.encryptor()

        # Pad and encrypt the ZIP archive data
        padder = padding.PKCS7(algorithms.AES.block_size).padder()
        padded_data = padder.update(zip_data) + padder.finalize()
        encrypted_data = encryptor.update(padded_data) + encryptor.finalize()

        return encrypted_data, hashed_key

    def decrypt_file(self, encrypted_data, hashed_key):
        # Create a cipher object using AES-256 in CBC mode
        backend = default_backend()
        cipher = Cipher(algorithms.AES(hashed_key), modes.CBC(
            hashed_key[:16]), backend=backend)
        decryptor = cipher.decryptor()

        # Decrypt the file data
        decrypted_data = decryptor.update(
            encrypted_data) + decryptor.finalize()

        # Remove the padding from the decrypted data
        unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
        unpadded_data = unpadder.update(decrypted_data) + unpadder.finalize()

        # Extract the original file from the decrypted ZIP archive
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            with zipfile.ZipFile(temp_file, 'w') as zip_file:
                zip_file.writestr('file', unpadded_data)

            with zip_file.open('file', 'r') as f:
                original_file_data = f.read()

        return original_file_data


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
        key = request.form["encrypt_key"]
        encryption_handler = EncryptionHandler(key)
        encrypted_file, hashed_key = encryption_handler.encrypt_file(
            file.read())

        # Save the encrypted file and the hashed key to the database
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO scripts (filename, data, mimetype, encrypted, encrypt_key) VALUES (%s, %s, %s, %s, %s)",
            (file.filename, psycopg2.Binary(encrypted_file),
             file.mimetype, True, psycopg2.Binary(hashed_key)),
        )
        conn.commit()
        cur.close()
        conn.close()
    else:
        # Save the file without encryption
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO scripts (filename, data, mimetype) VALUES (%s, %s, %s)",
            (file.filename, file.read(), file.mimetype),
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
        "SELECT filename, data, mimetype, encrypted, encrypt_key FROM scripts WHERE id = %s",
        (id,)
    )
    file = cur.fetchone()
    cur.close()
    conn.close()

    if file:
        if file[3]:  # File is encrypted
            encryption_handler = EncryptionHandler("")
            decrypted_data = encryption_handler.decrypt_file(file[1], file[4])
            return send_file(
                io.BytesIO(decrypted_data),
                mimetype=file[2],
                as_attachment=True,
                download_name=file[0],
            )
        else:  # File is not encrypted
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
