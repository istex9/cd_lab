from flask import Flask, jsonify, request, render_template, redirect, url_for, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import os
from ultralytics import YOLO
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from celery import Celery
from sqlalchemy import ForeignKey

def make_celery(app):
    celery = Celery(
        app.import_name,
        backend=app.config['CELERY_RESULT_BACKEND'],
        broker=app.config['CELERY_BROKER_URL']
    )
    celery.conf.update(app.config)
    return celery


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['DETECTION_FOLDER'] = 'runs/detect/predict/'
app.config['SECRET_KEY'] = 'your_very_secret_key_here'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Flask app konfigurációja
app.config['CELERY_BROKER_URL'] = 'redis://localhost:6379/0'
app.config['CELERY_RESULT_BACKEND'] = 'redis://localhost:6379/0'
celery = make_celery(app)

db = SQLAlchemy(app)
model = YOLO("yolov8x-worldv2.pt")

    
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    viewed_images = db.relationship('ImageEntry', secondary='viewed_entries', back_populates='viewers')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    

class ImageEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    original_image_path = db.Column(db.String(100), nullable=False)
    detected_image_path = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(300), nullable=False)
    car_count = db.Column(db.Integer, nullable=False, default=0)
    viewers = db.relationship('User', secondary='viewed_entries', back_populates='viewed_images')


class ViewedEntry(db.Model):
    __tablename__ = 'viewed_entries'
    user_id = db.Column(db.Integer, ForeignKey('user.id'), primary_key=True)
    image_id = db.Column(db.Integer, ForeignKey('image_entry.id'), primary_key=True)
    viewed = db.Column(db.Boolean, default=True)

    user = db.relationship('User', backref=db.backref('viewed_entry_links', lazy='dynamic'))
    image = db.relationship('ImageEntry', backref=db.backref('viewed_entry_links', lazy='dynamic'))


login_manager = LoginManager(app)
login_manager.login_view = 'login'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "UP"}), 200


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        is_admin = 'is_admin' in request.form

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return render_template('register.html', error='This username is already taken')

        new_user = User(username=username, is_admin=is_admin)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            # Átirányítás az admin dashboardra, ha az illető admin
            if user.is_admin:
                return redirect(url_for('admin_dashboard'))
            # Átirányítás az index oldalra, ha nem admin
            else:
                return redirect(url_for('index'))
        else:
            return render_template('login.html', error='Invalid username or password')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/admin_dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        return 'Access denied', 403
    
    unviewed_images = ImageEntry.query.filter(~ImageEntry.viewers.any(User.id == current_user.id)).all()
    viewed_images = current_user.viewed_images  # Már megtekintett képek lekérése

    return render_template('admin_dashboard.html', unviewed_images=unviewed_images, viewed_images=viewed_images)


# Ensure the upload and detection folders exist
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])
if not os.path.exists(app.config['DETECTION_FOLDER']):
    os.makedirs(app.config['DETECTION_FOLDER'])


with app.app_context():
    db.create_all()


@app.route('/')
@login_required
def index():
    images = ImageEntry.query.all()
    return render_template('index.html', images=images)


@app.route('/upload', methods=['POST'])
@login_required
def upload():
    if 'image' in request.files:
        image = request.files['image']
        description = request.form['description']
        if image and description:
            filename = secure_filename(image.filename)
            original_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            detected_path = os.path.join(app.config['DETECTION_FOLDER'], filename)
            image.save(original_path)
            car_count = detect_cars(original_path, detected_path)
            entry = ImageEntry(original_image_path=filename, detected_image_path=filename,
                description=description, car_count=car_count)
            db.session.add(entry)
            db.session.commit()
            return redirect(url_for('index'))
    return 'Failed to upload image'


@app.route('/mark_viewed/<int:image_id>', methods=['POST'])
@login_required
def mark_viewed(image_id):
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    image = ImageEntry.query.get(image_id)
    if image not in current_user.viewed_images:
        current_user.viewed_images.append(image)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Image marked as viewed'})
    return jsonify({'success': False, 'message': 'Image not found'}), 404


@app.route('/delete/<int:image_id>', methods=['POST'])
@login_required
def delete_image(image_id):
    image_to_delete = ImageEntry.query.get(image_id)
    if image_to_delete:
        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], image_to_delete.original_image_path))
        os.remove(os.path.join(app.config['DETECTION_FOLDER'], image_to_delete.detected_image_path))
        db.session.delete(image_to_delete)
        db.session.commit()
        return redirect(url_for('index'))
    return 'Image not found', 404


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    path = os.path.join(app.config['DETECTION_FOLDER'], filename)
    if os.path.exists(path):
        return send_from_directory(app.config['DETECTION_FOLDER'], filename)
    return 'File not found', 404


@celery.task
def detect_cars(original_image_path, detected_image_path):
    results = model(original_image_path, save_dir=detected_image_path, classes=2, save=True, exist_ok=True)
    names = model.names
    car_id = list(names)[list(names.values()).index('car')]
    #    count 'car' objects in the results
    count = results[0].boxes.cls.tolist().count(car_id)
    return count


if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5000, )
