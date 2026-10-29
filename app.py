import json
import os
from datetime import timezone
from zoneinfo import ZoneInfo
from datetime import datetime, timezone
from time import perf_counter
from functools import lru_cache
from pathlib import Path
from threading import Lock
from uuid import UUID, uuid4
from db import get_generations, save_generation
from mysql.connector import Error as MySQLError
from flask import (
    Flask,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from PIL import Image, UnidentifiedImageError
from nst import build_extractor, generate_image, load_image, tensor_to_image


app = Flask(__name__)

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

UPLOAD_FOLDER = Path(app.root_path) / "uploads"

generation_lock = Lock()


@lru_cache(maxsize=1)
def get_extractor():
    return build_extractor()


def read_image(uploaded_file):
    with Image.open(uploaded_file.stream) as image:
        if image.format not in {"JPEG", "PNG"}:
            raise ValueError("Only JPEG and PNG images are supported.")

        if image.width * image.height > 20_000_000:
            raise ValueError("Image exceeds 20 megapixels.")

        image.load()
        return image.convert("RGB")

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/create", methods=["GET", "POST"])
def create():
    message = None
    result_url = None
    download_url = None
    run_details = None

    if request.method == "POST":
        content_file = request.files.get("content_image")
        iterations_text = request.form.get("iterations", "50")
        style_weight_text = request.form.get("style_weight", "0.01")

        allowed_iterations = {"50", "100", "300", "500"}
        allowed_style_weights = {"0.001", "0.01", "0.1"}

        if (
            iterations_text not in allowed_iterations
            or style_weight_text not in allowed_style_weights
        ):
            return render_template(
                "create.html",
                message="Please choose valid generation settings.",
                result_url=None,
                download_url=None,
            ), 400

        iterations = int(iterations_text)
        style_weight = float(style_weight_text)
        style_file = request.files.get("style_image")

        if (
            content_file is None
            or style_file is None
            or not content_file.filename
            or not style_file.filename
        ):
            message = "Please select both images."
        else:
            try:
                content_image = read_image(content_file)
                style_image = read_image(style_file)
            except (
                UnidentifiedImageError,
                OSError,
                ValueError,
                Image.DecompressionBombError,
            ):
                message = (
                    "Please select readable JPEG or PNG images "
                    "with no more than 20 megapixels each."
                )
            else:
                try:
                    run_id = uuid4()
                    run_folder = UPLOAD_FOLDER / run_id.hex
                    run_folder.mkdir(parents=True, exist_ok=False)

                    content_path = run_folder / "content.png"
                    style_path = run_folder / "style.png"
                    output_path = run_folder / "generated.png"

                    content_image.save(content_path)
                    style_image.save(style_path)

                    with generation_lock:
                        extractor = get_extractor()

                        start_time = perf_counter()

                        content_tensor = load_image(content_path)
                        style_tensor = load_image(style_path)

                        generated = generate_image(
                            extractor,
                            content_tensor,
                            style_tensor,
                            iterations=iterations,
                            style_weight=style_weight,
                        )

                        tensor_to_image(generated).save(output_path)

                        runtime_seconds = perf_counter() - start_time

                    run_details = {
                        "run_id": run_id.hex,
                        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                        "iterations": iterations,
                        "style_weight": style_weight,
                        "content_weight": 1e4,
                        "total_variation_weight": 30,
                        "max_dimension": 256,
                        "runtime_seconds": round(runtime_seconds, 2),
                    }

                    metadata_path = run_folder / "metadata.json"

                    with metadata_path.open("w", encoding="utf-8") as file:
                        json.dump(run_details, file, indent=4)

                    result_url = url_for("generated_file", run_id=run_id)

                    download_url = url_for(
                        "generated_file",
                        run_id=run_id,
                        download="1",
                    )

                    message = "Your stylised image is ready."

                    try:
                        save_generation(run_details)
                    except MySQLError:
                        app.logger.exception(
                            "Could not save generation to MySQL"
                        )

                        message = (
                            "Your stylised image is ready, but saving "
                            "its database history failed."
                        )

                except Exception:
                    app.logger.exception("Style transfer failed")
                    message = (
                        "Image generation failed. "
                        "Check the VS Code terminal for details."
                    )

    return render_template(
        "create.html",
        message=message,
        result_url=result_url,
        download_url=download_url,
        run_details=run_details,
    )


@app.route("/generated/<uuid:run_id>")
def generated_file(run_id):
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
        records = get_generations()

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