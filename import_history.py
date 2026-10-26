import json
from pathlib import Path
from uuid import UUID

from mysql.connector import IntegrityError

from db import save_generation


def import_history():
    upload_folder = Path(__file__).resolve().parent / "uploads"

    imported = 0
    duplicates = 0
    skipped = 0

    for metadata_path in upload_folder.glob("*/metadata.json"):
        try:
            with metadata_path.open("r", encoding="utf-8") as file:
                details = json.load(file)

            run_id = UUID(details["run_id"]).hex
            run_folder = metadata_path.parent

            if run_folder.name != run_id:
                raise ValueError("Run ID does not match its folder.")

            required_images = [
                "content.png",
                "style.png",
                "generated.png",
            ]

            if not all(
                (run_folder / filename).is_file()
                for filename in required_images
            ):
                raise ValueError("One or more image files are missing.")

            details["run_id"] = run_id

            save_generation(details)

        except IntegrityError as error:
            if error.errno == 1062:
                duplicates += 1
                print("Already saved:", metadata_path.parent.name)
            else:
                raise

        except (OSError, ValueError, KeyError, TypeError) as error:
            skipped += 1
            print("Skipped:", metadata_path.parent.name, "-", error)

        else:
            imported += 1
            print("Imported:", run_id)

    print()
    print("New records imported:", imported)
    print("Already in database:", duplicates)
    print("Invalid or incomplete records skipped:", skipped)


if __name__ == "__main__":
    import_history()