
import os
import json
import uuid
import time
from pathlib import Path
from functools import wraps

import cv2
from ultralytics import YOLO

from flask import (
    Flask, render_template, request,
    redirect, url_for, session, flash,
    send_from_directory
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)
from werkzeug.utils import secure_filename

from database import initialize_database, get_connection


# -----------------------------------
# APPLICATION CONFIGURATION
# -----------------------------------

app = Flask(__name__)

app.secret_key = os.environ.get(
    "CITINOVA_SECRET_KEY",
    "development-key-change-before-deployment"
)

app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024

initialize_database()


# -----------------------------------
# VIDEO DETECTION CONFIGURATION
# -----------------------------------

BASE_DIR = Path(__file__).resolve().parent

UPLOAD_DIR = BASE_DIR / "data" / "uploads"
RESULT_DIR = BASE_DIR / "results" / "vehicle_detection"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
RESULT_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_VIDEO_EXTENSIONS = {
    ".mp4", ".avi", ".mov", ".mkv", ".webm"
}

# Load YOLO model once when the application starts.
vehicle_model = YOLO("yolo11n.pt")


# -----------------------------------
# ROLE PROTECTION
# -----------------------------------

def login_required(role=None):

    def decorator(function):

        @wraps(function)
        def wrapper(*args, **kwargs):

            if "user_id" not in session:
                flash("Please log in first.", "error")
                return redirect(url_for("home"))

            if role and session.get("role") != role:
                flash(
                    "You are not authorized to access this page.",
                    "error"
                )
                return redirect(url_for("home"))

            return function(*args, **kwargs)

        return wrapper

    return decorator


# -----------------------------------
# HOME PAGE
# -----------------------------------

@app.route("/")
def home():
    return render_template("index.html")


# -----------------------------------
# REGISTRATION - CITIZENS ONLY
# -----------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("Please complete all fields.", "error")
            return render_template("register.html")

        if len(password) < 8:
            flash("Password must contain at least 8 characters.", "error")
            return render_template("register.html")

        password_hash = generate_password_hash(password)

        connection = get_connection()

        try:

            connection.execute(
                """
                INSERT INTO users (name, email, password_hash, role)
                VALUES (?, ?, ?, 'citizen')
                """,
                (name, email, password_hash)
            )

            connection.commit()

            flash(
                "Registration successful. Please log in.",
                "success"
            )

            return redirect(url_for("login", role="citizen"))

        except Exception as error:

            if "UNIQUE constraint failed" in str(error):
                flash(
                    "An account with this email already exists.",
                    "error"
                )
            else:
                app.logger.exception("Registration failed")
                flash(
                    "Registration failed. Please try again.",
                    "error"
                )

        finally:
            connection.close()

    return render_template("register.html")


# -----------------------------------
# LOGIN - CITIZEN / AUTHORITY
# -----------------------------------

@app.route("/login/<role>", methods=["GET", "POST"])
def login(role):

    if role not in ("citizen", "authority"):
        return "Invalid user role", 404

    if request.method == "POST":

        email = request.form.get(
            "email", ""
        ).strip().lower()

        password = request.form.get("password", "")

        connection = get_connection()

        user = connection.execute(
            """
            SELECT * FROM users
            WHERE email = ? AND role = ?
            """,
            (email, role)
        ).fetchone()

        connection.close()

        if user and check_password_hash(
            user["password_hash"], password
        ):

            session.clear()

            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]

            if role == "authority":
                return redirect(
                    url_for("authority_dashboard")
                )

            return redirect(
                url_for("citizen_dashboard")
            )

        flash("Invalid email or password.", "error")

    return render_template("login.html", role=role)


# -----------------------------------
# CITIZEN DASHBOARD
# -----------------------------------

@app.route("/citizen/dashboard")
@login_required(role="citizen")
def citizen_dashboard():

    connection = get_connection()

    reports = connection.execute(
        """
        SELECT * FROM road_reports
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (session["user_id"],)
    ).fetchall()

    connection.close()

    return render_template(
        "citizen_dashboard.html",
        reports=reports
    )


# -----------------------------------
# AUTHORITY DASHBOARD
# -----------------------------------

@app.route("/authority/dashboard")
@login_required(role="authority")
def authority_dashboard():

    connection = get_connection()

    total_users = connection.execute(
        """
        SELECT COUNT(*) FROM users
        WHERE role = 'citizen'
        """
    ).fetchone()[0]

    total_reports = connection.execute(
        "SELECT COUNT(*) FROM road_reports"
    ).fetchone()[0]

    pending_reports = connection.execute(
        """
        SELECT COUNT(*) FROM road_reports
        WHERE status = 'Pending'
        """
    ).fetchone()[0]

    connection.close()

    return render_template(
        "authority_dashboard.html",
        total_users=total_users,
        total_reports=total_reports,
        pending_reports=pending_reports
    )


# -----------------------------------
# LOGOUT
# -----------------------------------

@app.route("/logout")
def logout():

    session.clear()

    flash("You have been logged out.", "success")

    return redirect(url_for("home"))


# -----------------------------------
# AUTHORITY TRAFFIC MAP
# -----------------------------------

@app.route("/authority/map")
@login_required(role="authority")
def authority_map():

    return render_template("traffic_map.html")


# -----------------------------------
# AI TRAFFIC DETECTION PAGE
# -----------------------------------

@app.route("/authority/traffic-detection")
@login_required(role="authority")
def traffic_detection():

    return render_template("traffic_detection.html")


# -----------------------------------
# PROCESS UPLOADED TRAFFIC VIDEO
# -----------------------------------

@app.route(
    "/authority/process-traffic-video",
    methods=["POST"]
)
@login_required(role="authority")
def process_traffic_video():

    video = request.files.get("traffic_video")

    if not video or not video.filename:
        flash("Please select a traffic video.", "error")
        return redirect(url_for("traffic_detection"))

    safe_filename = secure_filename(video.filename)
    extension = Path(safe_filename).suffix.lower()

    if extension not in ALLOWED_VIDEO_EXTENSIONS:
        flash("Unsupported video format.", "error")
        return redirect(url_for("traffic_detection"))

    unique_name = uuid.uuid4().hex

    input_path = UPLOAD_DIR / f"{unique_name}{extension}"
    output_path = RESULT_DIR / f"{unique_name}_detected.mp4"
    json_path = RESULT_DIR / f"{unique_name}_statistics.json"

    video.save(input_path)

    cap = cv2.VideoCapture(str(input_path))

    if not cap.isOpened():

        cap.release()
        input_path.unlink(missing_ok=True)

        flash("Unable to read the uploaded video.", "error")
        return redirect(url_for("traffic_detection"))

    fps = cap.get(cv2.CAP_PROP_FPS)

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    total_frames = int(
        cap.get(cv2.CAP_PROP_FRAME_COUNT)
    )

    if width <= 0 or height <= 0:

        cap.release()
        input_path.unlink(missing_ok=True)

        flash("Invalid video dimensions.", "error")
        return redirect(url_for("traffic_detection"))

    if fps <= 0:
        fps = 25

    writer = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        min(fps, 15),
        (width, height)
    )

    if not writer.isOpened():

        cap.release()
        writer.release()
        input_path.unlink(missing_ok=True)

        flash("Unable to create processed video.", "error")
        return redirect(url_for("traffic_detection"))

    class_names = {
        2: "Car",
        3: "Motorcycle",
        5: "Bus",
        7: "Truck"
    }

    totals = {
        name: 0 for name in class_names.values()
    }

    frames_processed = 0
    total_detections = 0

    start = time.time()

    try:

        while frames_processed < min(total_frames, 300):

            success, frame = cap.read()

            if not success:
                break

            results = vehicle_model.predict(
                frame,
                imgsz=640,
                conf=0.35,
                classes=list(class_names.keys()),
                device="cpu",
                verbose=False
            )

            result = results[0]
            annotated = result.plot()

            frame_count = 0

            if result.boxes is not None:

                for cls in result.boxes.cls.tolist():

                    name = class_names.get(int(cls))

                    if name:

                        totals[name] += 1
                        total_detections += 1
                        frame_count += 1

            cv2.putText(
                annotated,
                f"Vehicles in frame: {frame_count}",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                (0, 255, 0),
                2
            )

            writer.write(annotated)

            frames_processed += 1

    except Exception:

        app.logger.exception("YOLO video processing failed")

        flash(
            "An error occurred during video processing.",
            "error"
        )

        output_path.unlink(missing_ok=True)
        json_path.unlink(missing_ok=True)

        return redirect(url_for("traffic_detection"))

    finally:

        cap.release()
        writer.release()
        input_path.unlink(missing_ok=True)

    if frames_processed == 0:

        output_path.unlink(missing_ok=True)

        flash("No readable video frames were found.", "error")
        return redirect(url_for("traffic_detection"))

    elapsed = round(time.time() - start, 2)

    statistics = {
        "frames_processed": frames_processed,
        "total_detection_instances": total_detections,
        "average_vehicles_per_frame": round(
            total_detections / frames_processed, 2
        ),
        "class_detection_instances": totals,
        "processing_time_seconds": elapsed,
        "note": (
            "Detection instances across frames, "
            "not unique vehicles."
        )
    }

    json_path.write_text(
        json.dumps(statistics, indent=4),
        encoding="utf-8"
    )

    return render_template(
        "traffic_detection_result.html",
        statistics=statistics,
        video_filename=output_path.name
    )


# -----------------------------------
# SERVE PROCESSED TRAFFIC VIDEO
# -----------------------------------

@app.route(
    "/authority/processed-video/<filename>"
)
@login_required(role="authority")
def processed_traffic_video(filename):

    if Path(filename).name != filename:
        return "Invalid filename", 400

    if not filename.endswith("_detected.mp4"):
        return "Invalid video file", 400

    return send_from_directory(
        RESULT_DIR,
        filename,
        mimetype="video/mp4"
    )


# -----------------------------------
# RUN APPLICATION
# IMPORTANT: KEEP THIS AT THE VERY END
# -----------------------------------

if __name__ == "__main__":
    app.run(
        debug=True,
        use_reloader=False
    )
