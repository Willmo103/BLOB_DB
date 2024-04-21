import os
import logging
from cryptography.hazmat.primitives import padding
import hashlib
import io
from os import getenv
from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, send_file, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import FileField, BooleanField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length, ValidationError
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import zipfile
import tempfile

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
print(os.path.join(ROOT_DIR, '.env'))
load_dotenv(os.path.join(ROOT_DIR, '.env'))

# Configure logger
if os.getenv("FLASK_ENV") == "development":
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
else:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__, template_folder="../templates")
app.config['SQLALCHEMY_DATABASE_URI'] = getenv("SQLALCHEMY_DATABASE_URI")
app.config['SECRET_KEY'] = getenv("SECRET_KEY")
db = SQLAlchemy(app)

logger = logging.getLogger(__name__)

# Add file handler to log to a file with the date
file_handler = logging.FileHandler('app.log')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)


class Script(db.Model):
    __tablename__ = 'scripts'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255))
    data = db.Column(db.LargeBinary)
    mimetype = db.Column(db.String(50))
    encrypted = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    encryption_key = db.relationship('EncryptionKey', uselist=False, back_populates='script')


class EncryptionKey(db.Model):
    __tablename__ = 'encryption_keys'
    id = db.Column(db.Integer, primary_key=True)
    script_id = db.Column(db.Integer, db.ForeignKey('scripts.id'))
    encrypt_key = db.Column(db.LargeBinary)
    script = db.relationship('Script', back_populates='encryption_key')


def validate_encrypt_password(form, field):
    if form.encrypt.data and not field.data:
        raise ValidationError('Encryption password is required when encryption is enabled.')


class UploadForm(FlaskForm):
    file = FileField('File', validators=[DataRequired()])
    encrypt = BooleanField('Encrypt', default=False)
    encrypt_password = PasswordField('Encryption Password', validators=[Length(min=8), validate_encrypt_password])
    submit = SubmitField('Upload')


class DecryptForm(FlaskForm):
    decrypt_password = PasswordField('Decryption Password', validators=[DataRequired()])
    submit = SubmitField('Decrypt')


class DeleteForm(FlaskForm):
    decrypt_password = PasswordField('Deletion Password', validators=[DataRequired()])
    submit = SubmitField('Delete')


class EncryptionHandler:
    def __init__(self, key):
        self.key = key
        self.hashed_key = hashlib.sha256(key.strip().encode()).digest()
        logger.debug("EncryptionHandler initialized with key")

    def encrypt_file(self, file_data):
        logger.debug("Encrypting file")
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
        cipher = Cipher(algorithms.AES(self.hashed_key), modes.CBC(self.hashed_key[:16]), backend=backend)
        encryptor = cipher.encryptor()

        # Pad and encrypt the ZIP archive data
        padder = padding.PKCS7(algorithms.AES.block_size).padder()
        padded_data = padder.update(zip_data) + padder.finalize()
        encrypted_data = encryptor.update(padded_data) + encryptor.finalize()

        logger.debug("File encrypted")
        return encrypted_data

    def decrypt_file(self, encrypted_data):
        logger.debug("Decrypting file")
        # Create a cipher object using AES-256 in CBC mode
        backend = default_backend()
        cipher = Cipher(algorithms.AES(self.hashed_key), modes.CBC(self.hashed_key[:16]), backend=backend)
        decryptor = cipher.decryptor()

        # Decrypt the file data
        decrypted_data = decryptor.update(encrypted_data) + decryptor.finalize()

        # Remove the padding from the decrypted data
        unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
        unpadded_data = unpadder.update(decrypted_data) + unpadder.finalize()

        # Extract the original file from the decrypted ZIP archive
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(unpadded_data)
            temp_file.seek(0)

            with zipfile.ZipFile(temp_file, 'r') as zip_file:
                original_file_data = zip_file.read('file')

        logger.debug("File decrypted")
        return original_file_data

    def check_password(self, password):
        return hashlib.sha256(password.strip().encode()).digest() == self.hashed_key


@ app.route("/", methods=["GET", "POST"])
def index():
    upload_form = UploadForm()
    decrypt_form = DecryptForm()
    delete_form = DeleteForm()
    if request.method == "GET":
        try:
            scripts = Script.query.all()
            logger.debug("Rendering template")
            return render_template("index.html", upload_form=upload_form, decrypt_form=decrypt_form, delete_form=delete_form, scripts=scripts)
        except Exception as e:
            logger.error(f"Error in rendering template: {str(e)}", stack_info=True)
    if request.method == "POST":
        try:
            if upload_form.validate_on_submit():
                try:
                    filename = upload_form.file.data.filename
                    # logger.debug(f'Saving file: {filename}')
                    file = upload_form.file.data
                    if upload_form.encrypt.data:
                        key = upload_form.encrypt_password.data
                        encryption_handler = EncryptionHandler(key)
                        encrypted_file = encryption_handler.encrypt_file(file.read())
                        script = Script(filename=filename, data=encrypted_file, mimetype=file.mimetype, encrypted=True)
                        encryption_key = EncryptionKey(encrypt_key=encryption_handler.hashed_key)
                        script.encryption_key = encryption_key
                        db.session.add(script)
                        db.session.commit()
                        logger.debug(f"File saved and encrypted: {filename}, mimetype: {file.mimetype}, encrypted: True")
                except Exception as e:
                    logger.error(f"Error in upload_form.validate_on_submit: {str(e)}", stack_info=True)

            elif not upload_form.encrypt.data:
                logger.debug("File not encrypted")
                try:
                    filename = upload_form.file.data.filename
                    file = upload_form.file.data
                    logging.debug(f'Saving file(Not Encrypted): {filename}')
                    script = Script(filename=filename, data=file.read(), mimetype=file.mimetype)
                    db.session.add(script)
                    db.session.commit()
                    logger.debug(f"File saved: {filename}, mimetype: {file.mimetype}, encrypted: False")
                    return redirect(url_for("index"))
                except Exception as e:
                    logger.error(f"Error in upload_form.validate_on_submit: {str(e)}", stack_info=True)

        except Exception as e:
            logger.error(f"Error in index function: {str(e)}", stack_info=True)

        try:
            if delete_form.validate_on_submit():
                password = delete_form.decrypt_password.data
                script = Script.query.get(id)
                if script:
                    encryption_handler = EncryptionHandler(password)
                    if encryption_handler.hashed_key == script.encryption_key.encrypt_key:
                        db.session.delete(script)
                        db.session.commit()
                        logger.debug("File deleted")
                        return redirect(url_for("index"))
                    else:
                        return "Invalid decryption password", 400
                else:
                    return "File not found", 404
        except Exception as e:
            logger.error(f"Error in delete_form.validate_on_submit: {str(e)}", stack_info=True)

    return redirect(url_for("index"))


@ app.route("/download/<int:id>", methods=["POST"])
def download_file(id):
    logger.debug("Download file function called")
    decrypt_form = DecryptForm()
    script = Script.query.get(id)

    try:
        if script:
            logger.debug(f"File found: {script.filename}")
            if script.encrypted:
                logger.debug(f"File is encrypted: {script.filename}")
                if decrypt_form.validate_on_submit():
                    password = decrypt_form.decrypt_password.data
                    encryption_handler = EncryptionHandler(password)
                    if encryption_handler.hashed_key == script.encryption_key.encrypt_key:
                        decrypted_data = encryption_handler.decrypt_file(script.data)
                        logger.debug(f"File decrypted: {script.filename}, mimetype: {script.mimetype}")
                        return send_file(
                            io.BytesIO(decrypted_data),
                            mimetype=script.mimetype,
                            as_attachment=True,
                            download_name=script.filename,
                        )
                    else:
                        logger.debug(f"Invalid decryption password for file: {script.filename}")
                        return "Invalid decryption password", 400
                else:
                    logger.debug(f"Decryption password is required for file: {script.filename}")
                    return "Decryption password is required", 400
            else:
                logger.debug(f"File downloaded: {script.filename}, mimetype: {script.mimetype}")
                return send_file(
                    io.BytesIO(script.data),
                    mimetype=script.mimetype,
                    as_attachment=True,
                    download_name=script.filename,
                )
        else:
            logger.debug("File not found")
            return "File not found", 404
    except Exception as e:
        logger.error(f"Error in download_file function: {str(e)}", stack_info=True)


@ app.route("/delete/<int:id>", methods=["POST"])
def delete_file(id):
    delete_form = DeleteForm()
    script = Script.query.get(id)

    if script:
        if script.encrypted:
            if delete_form.validate_on_submit():
                password = delete_form.decrypt_password.data
                encryption_handler = EncryptionHandler(password)
                if encryption_handler.hashed_key == script.encryption_key.encrypt_key:
                    db.session.delete(script)
                    db.session.commit()
                    return redirect(url_for("index"))
                else:
                    return "Invalid deletion password", 400
            else:
                return "Deletion password is required", 400
        else:
            db.session.delete(script)
            db.session.commit()
            return redirect(url_for("index"))
    else:
        return "File not found", 404


@ app.route("/filename/<int:id>", methods=["GET"])
def get_filename(id):
    script = Script.query.get(id)
    if script:
        return jsonify({"filename": script.filename})
    else:
        return "File not found", 404


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000)
