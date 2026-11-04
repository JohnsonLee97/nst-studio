def queue_healthcheck():
    return {
        "message": "Background worker completed the test successfully."
    }

def generate_image_job(run_id, owner_id, iterations, style_weight):
    import json
    import logging
    from datetime import datetime, timezone
    from pathlib import Path
    from time import perf_counter
    from uuid import UUID

    from mysql.connector import Error as MySQLError

    from db import save_generation
    from nst import (
        build_extractor,
        generate_image,
        load_image,
        tensor_to_image,
    )

    logger = logging.getLogger(__name__)

    # Validate the ID before using it as a folder name.
    run_id = UUID(run_id).hex

    project_folder = Path(__file__).resolve().parent
    run_folder = project_folder / "uploads" / run_id

    content_path = run_folder / "content.png"
    style_path = run_folder / "style.png"
    output_path = run_folder / "generated.png"

    if not content_path.is_file() or not style_path.is_file():
        raise FileNotFoundError("Generation input images are missing.")

    extractor = build_extractor()

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

    temporary_output = run_folder / "generated.tmp.png"

    tensor_to_image(generated).save(temporary_output)
    temporary_output.replace(output_path)

    runtime_seconds = perf_counter() - start_time

    details = {
        "run_id": run_id,
        "owner_id": owner_id,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "iterations": iterations,
        "style_weight": style_weight,
        "content_weight": 1e4,
        "total_variation_weight": 30,
        "max_dimension": 256,
        "runtime_seconds": round(runtime_seconds, 2),
        "history_saved": False,
    }

    try:
        save_generation(details)
    except MySQLError:
        logger.exception("Could not save generation to MySQL")
    else:
        details["history_saved"] = True

    metadata_path = run_folder / "metadata.json"
    temporary_metadata = run_folder / "metadata.tmp.json"

    with temporary_metadata.open("w", encoding="utf-8") as file:
        json.dump(details, file, indent=4)

    temporary_metadata.replace(metadata_path)

    return {"run_id": run_id}