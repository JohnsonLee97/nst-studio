import json
import os
import shutil

from redis.exceptions import RedisError
from rq.exceptions import NoSuchJobError
from rq.job import Job
from rq.serializers import JSONSerializer

from queue_setup import (
    GenerationQueueFull,
    OwnerAlreadyGenerating,
    enqueue_generation,
    generation_queue,
    redis_connection,
)

from zoneinfo import ZoneInfo
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4
from secrets import token_hex
from db import get_generations
from mysql.connector import Error as MySQLError
from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from PIL import Image, UnidentifiedImageError

app = Flask(__name__)

app.config.update(
    SECRET_KEY=os.environ["FLASK_SECRET_KEY"],
    SESSION_COOKIE_NAME="nst_session",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

app.config["DISPLAY_TIMEZONE"] = os.environ["DISPLAY_TIMEZONE"]
display_timezone = ZoneInfo(app.config["DISPLAY_TIMEZONE"])

def format_local_time(utc_datetime):
    return (
        utc_datetime
        .replace(tzinfo=timezone.utc)
        .astimezone(display_timezone)
        .strftime("%d %b %Y, %I:%M:%S %p")
    )

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

app.config["IMAGE_RETENTION_HOURS"] = int(
    os.environ["IMAGE_RETENTION_HOURS"]
)

if app.config["IMAGE_RETENTION_HOURS"] <= 0:
    raise ValueError("IMAGE_RETENTION_HOURS must be greater than zero.")

app.config["JOB_POLL_INTERVAL_SECONDS"] = int(
    os.environ["JOB_POLL_INTERVAL_SECONDS"]
)

if app.config["JOB_POLL_INTERVAL_SECONDS"] <= 0:
    raise ValueError(
        "JOB_POLL_INTERVAL_SECONDS must be greater than zero."
    )

UPLOAD_FOLDER = Path(app.root_path) / "uploads"


def read_image(uploaded_file):
    with Image.open(uploaded_file.stream) as image:
        if image.format not in {"JPEG", "PNG"}:
            raise ValueError("Only JPEG and PNG images are supported.")

        if image.width * image.height > 20_000_000:
            raise ValueError("Image exceeds 20 megapixels.")

        image.load()
        return image.convert("RGB")

@app.before_request
def ensure_visitor_session():
    if request.endpoint in {"create", "history", "generated_file",  "generation_status"}:
        if "owner_id" not in session:
            session["owner_id"] = token_hex(32)

def load_owned_generation(run_id):
    run_folder = UPLOAD_FOLDER / run_id.hex
    metadata_path = run_folder / "metadata.json"

    try:
        with metadata_path.open("r", encoding="utf-8") as file:
            details = json.load(file)
    except FileNotFoundError:
        abort(404)
    except (OSError, json.JSONDecodeError):
        app.logger.exception("Could not read saved result metadata")
        abort(500)

    if not isinstance(details, dict):
        abort(404)

    if (
        details.get("run_id") != run_id.hex
        or details.get("owner_id") != session["owner_id"]
    ):
        abort(404)

    try:
        completed_at = datetime.fromisoformat(
            details["completed_at_utc"]
        )

        if completed_at.tzinfo is None:
            raise ValueError("Completion time must include a timezone.")

        expires_at = completed_at + timedelta(
            hours=app.config["IMAGE_RETENTION_HOURS"]
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        app.logger.exception("Invalid generation completion time")
        abort(500)

    if datetime.now(timezone.utc) >= expires_at:
        abort(404)

    if not (run_folder / "generated.png").is_file():
        abort(404)

    return details

@app.after_request
def prevent_private_result_caching(response):
    if request.endpoint in {"create", "history", "generated_file", "generation_status"}:
        response.headers["Cache-Control"] = "private, no-store"

    return response

@app.context_processor
def retention_template_settings():
    return {
        "image_retention_hours": app.config["IMAGE_RETENTION_HOURS"]
    }

def load_owned_job(run_id):
    job = Job.fetch(
        run_id.hex,
        connection=redis_connection,
        serializer=JSONSerializer,
    )

    if (
        job.origin != generation_queue.name
        or job.meta.get("owner_id") != session["owner_id"]
        or job.meta.get("run_id") != run_id.hex
    ):
        abort(404)

    return job

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/create", methods=["GET", "POST"])
def create():
    def show_page(message=None, status_code=200, pending_job=None):
        return render_template(
            "create.html",
            message=message,
            result_url=None,
            download_url=None,
            run_details=None,
            pending_job=pending_job,
        ), status_code

    if request.method == "GET":
        if "run_id" in request.args:
            try:
                run_id = UUID(request.args["run_id"])
            except ValueError:
                abort(404)

            run_details = load_owned_generation(run_id)

            message = "Your stylised image is ready."

            if run_details.get("history_saved", True) is False:
                message = (
                    "Your stylised image is ready, but saving "
                    "its database history failed."
                )

            return render_template(
                "create.html",
                message=message,
                result_url=url_for(
                    "generated_file",
                    run_id=run_id,
                ),
                download_url=url_for(
                    "generated_file",
                    run_id=run_id,
                    download="1",
                ),
                run_details=run_details,
                pending_job=None,
            )

        if "job_id" in request.args:
            try:
                run_id = UUID(request.args["job_id"])
            except ValueError:
                abort(404)

            try:
                load_owned_job(run_id)
            except NoSuchJobError:
                return show_page(
                    "This generation job has expired or is unavailable.",
                    status_code=404,
                )
            except RedisError:
                app.logger.exception("Could not load generation job")
                return show_page(
                    "Generation status is temporarily unavailable. "
                    "Refresh this page to try again.",
                    status_code=503,
                )

            return show_page(
                pending_job={
                    "status_url": url_for(
                        "generation_status",
                        run_id=run_id,
                    ),
                },
            )

        return show_page()

    iterations_text = request.form.get("iterations", "")
    style_weight_text = request.form.get("style_weight", "")

    allowed_iterations = {"50", "100", "300", "500"}
    allowed_style_weights = {"0.001", "0.01", "0.1"}

    if (
        iterations_text not in allowed_iterations
        or style_weight_text not in allowed_style_weights
    ):
        return show_page(
            "Please choose valid generation settings.",
            status_code=400,
        )

    content_file = request.files.get("content_image")
    style_file = request.files.get("style_image")

    if (
        content_file is None
        or style_file is None
        or not content_file.filename
        or not style_file.filename
    ):
        return show_page(
            "Please select both images.",
            status_code=400,
        )

    try:
        content_image = read_image(content_file)
        style_image = read_image(style_file)
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
    ):
        return show_page(
            "Please select readable JPEG or PNG images "
            "with no more than 20 megapixels each.",
            status_code=400,
        )

    run_id = uuid4()
    run_folder = UPLOAD_FOLDER / run_id.hex

    try:
        run_folder.mkdir(parents=True, exist_ok=False)

        request_details = {
            "run_id": run_id.hex,
            "owner_id": session["owner_id"],
            "submitted_at_utc": datetime.now(timezone.utc).isoformat(),
        }

        temporary_request = run_folder / "request.tmp.json"

        with temporary_request.open("w", encoding="utf-8") as file:
            json.dump(request_details, file, indent=4)

        temporary_request.replace(run_folder / "request.json")

        content_image.save(run_folder / "content.png")
        style_image.save(run_folder / "style.png")

    except OSError:
        app.logger.exception("Could not save generation inputs")
        return show_page(
            "Your images could not be saved. Please try again.",
            status_code=500,
        )

    try:
        enqueue_generation(
            run_id.hex,
            session["owner_id"],
            int(iterations_text),
            float(style_weight_text),
        )

    except OwnerAlreadyGenerating as error:
        shutil.rmtree(run_folder)

        return redirect(
            url_for("create", job_id=error.job_id),
            code=303,
        )

    except GenerationQueueFull:
        shutil.rmtree(run_folder)

        return show_page(
            "The generation queue is full. Please try again later.",
            status_code=503,
        )

    except RedisError:
        app.logger.exception(
            "Could not confirm whether generation was queued"
        )

        # The submission may have reached Redis before the
        # connection failed, so keep its input files.
        return show_page(
            "We could not confirm your submission. "
            "Please wait before trying again.",
            status_code=503,
        )

    return redirect(
        url_for("create", job_id=run_id.hex),
        code=303,
    )

@app.route("/jobs/<uuid:run_id>")
def generation_status(run_id):
    try:
        job = load_owned_job(run_id)
        status = job.get_status()

    except NoSuchJobError:
        return jsonify(
            status="unavailable",
            message="This generation job has expired or is unavailable.",
        ), 404

    except RedisError:
        app.logger.exception("Could not read generation status")

        return jsonify(
            status="unavailable",
            message="Generation status is temporarily unavailable.",
        ), 503

    if status == "finished":
        load_owned_generation(run_id)

        return jsonify(
            status="finished",
            result_url=url_for(
                "create",
                run_id=run_id.hex,
            ),
        )

    if status in {"failed", "stopped", "canceled"}:
        return jsonify(
            status="failed",
            message="Image generation failed. Please try again.",
        )

    if status in {
        "queued",
        "deferred",
        "scheduled",
        "ready_to_enqueue",
    }:
        return jsonify(status="queued")

    if status == "started":
        return jsonify(status="generating")

    return jsonify(
        status="unavailable",
        message="This generation job is unavailable.",
    ), 404

@app.route("/generated/<uuid:run_id>")
def generated_file(run_id):
    load_owned_generation(run_id)

    run_folder = UPLOAD_FOLDER / run_id.hex

    return send_from_directory(
        str(run_folder),
        "generated.png",
        as_attachment=request.args.get("download") == "1",
    )

@app.route("/history")
def history():
    runs = []
    error_message = None
    status_code = 200

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(
            hours=app.config["IMAGE_RETENTION_HOURS"]
        )

        records = get_generations(
            session["owner_id"],
            cutoff,
        )

        for record in records:
            run_id = UUID(record["run_id"])

            runs.append({
                "completed_at": format_local_time(record["completed_at_utc"]),
                "iterations": record["iterations"],
                "style_weight": record["style_weight"],
                "runtime_seconds": record["runtime_seconds"],
                "image_url": url_for(
                    "generated_file",
                    run_id=run_id,
                ),
                "download_url": url_for(
                    "generated_file",
                    run_id=run_id,
                    download="1",
                ),
            })

    except MySQLError:
        app.logger.exception("Could not load generation history")
        error_message = "History is temporarily unavailable. Please try again."
        status_code = 503

    return render_template(
        "history.html",
        runs=runs,
        error_message=error_message,
        display_timezone=app.config["DISPLAY_TIMEZONE"],
    ), status_code

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/experiments")
def experiments():
    data_path = Path(app.root_path) / "data" / "experiments.json"

    with data_path.open("r", encoding="utf-8") as file:
        experiment = json.load(file)

    return render_template(
        "experiments.html",
        experiment=experiment,
    )

if __name__ == "__main__":
    app.run(debug=True)