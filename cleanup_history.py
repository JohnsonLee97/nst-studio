import json
import os
import argparse
import shutil

from mysql.connector import Error as MySQLError
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from db import get_connection


PROJECT_FOLDER = Path(__file__).resolve().parent
UPLOAD_FOLDER = PROJECT_FOLDER / "uploads"


def parse_completion(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)

    if not isinstance(value, datetime):
        raise ValueError("Invalid completion time.")

    # MySQL stores UTC timestamps without timezone information.
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)

def delete_expired_run(run_id, folder, has_record, cutoff):
    cutoff_utc = cutoff.astimezone(
        timezone.utc
    ).replace(tzinfo=None)

    with get_connection() as connection:
        try:
            with connection.cursor() as cursor:
                if has_record:
                    cursor.execute(
                        """
                        DELETE FROM generations
                        WHERE run_id = %s
                          AND completed_at_utc <= %s
                        """,
                        (run_id, cutoff_utc),
                    )

                    if cursor.rowcount != 1:
                        connection.rollback()
                        return False

                if folder is not None:
                    if (
                        folder.parent.resolve() != UPLOAD_FOLDER.resolve()
                        or folder.name != run_id
                        or folder.is_symlink()
                    ):
                        raise ValueError("Unsafe upload folder path.")

                    if folder.exists():
                        shutil.rmtree(folder)

            connection.commit()
            return True

        except Exception:
            connection.rollback()
            raise

def preview_cleanup(delete=False):
    retention_hours = int(os.environ["IMAGE_RETENTION_HOURS"])

    if retention_hours <= 0:
        raise ValueError("IMAGE_RETENTION_HOURS must be greater than zero.")

    cutoff = datetime.now(timezone.utc) - timedelta(
        hours=retention_hours
    )

    with get_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(
                "SELECT run_id, completed_at_utc FROM generations"
            )
            records = cursor.fetchall()

    database_records = {
        record["run_id"]: record
        for record in records
    }

    folders = {}

    if UPLOAD_FOLDER.exists():
        for folder in UPLOAD_FOLDER.iterdir():
            if folder.is_symlink() or not folder.is_dir():
                continue

            try:
                valid_name = UUID(folder.name).hex == folder.name
            except ValueError:
                valid_name = False

            if valid_name:
                folders[folder.name] = folder

    if delete:
        # Check DELETE permission before removing any files.
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM generations WHERE 1 = 0"
                )
            connection.rollback()

    run_ids = sorted(set(database_records) | set(folders))
    expired_count = 0
    skipped_count = 0
    deleted_count = 0
    failed_count = 0

    print(f"Retention: {retention_hours} hours")
    print(f"UTC cutoff: {cutoff.isoformat()}")
    print()

    for run_id in run_ids:
        record = database_records.get(run_id)
        folder = folders.get(run_id)
        completion_times = []

        try:
            if record is not None:
                completion_times.append(
                    parse_completion(record["completed_at_utc"])
                )

            if folder is not None:
                metadata_path = folder / "metadata.json"

                if metadata_path.is_symlink():
                    raise ValueError("Metadata is a symbolic link.")

                if metadata_path.exists():
                    with metadata_path.open(
                        encoding="utf-8"
                    ) as file:
                        details = json.load(file)

                    if (
                        not isinstance(details, dict)
                        or details.get("run_id") != run_id
                    ):
                        raise ValueError("Metadata run ID does not match.")

                    completion_times.append(
                        parse_completion(details["completed_at_utc"])
                    )

            if not completion_times:
                raise ValueError("No completion timestamp available.")

        except (
            OSError,
            KeyError,
            TypeError,
            ValueError,
            OverflowError,
        ) as error:
            print(f"SKIPPED {run_id}: {error}")
            skipped_count += 1
            continue

        # If timestamps differ, use the newer one to avoid early deletion.
        if max(completion_times) > cutoff:
            continue

        expired_count += 1

        print(f"EXPIRED {run_id}")
        print(f"  Upload folder: {'yes' if folder else 'no'}")
        print(f"  Database record: {'yes' if record else 'no'}")

        if delete:
            try:
                removed = delete_expired_run(
                    run_id,
                    folder,
                    record is not None,
                    cutoff,
                )
            except (OSError, ValueError, MySQLError) as error:
                print(f"  FAILED: {error}")
                failed_count += 1
            else:
                if removed:
                    print("  DELETED")
                    deleted_count += 1
                else:
                    print("  SKIPPED: database record changed or disappeared.")
                    skipped_count += 1

    print()
    print(f"Expired runs: {expired_count}")
    print(f"Skipped runs needing review: {skipped_count}")
    if delete:
        print(f"Deleted runs: {deleted_count}")
        print(f"Failed deletions: {failed_count}")
    else:
        print("Preview only. No files or database records were deleted.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Preview or delete expired generation history."
    )

    parser.add_argument(
        "--delete",
        action="store_true",
        help="Permanently delete expired upload folders and records.",
    )

    args = parser.parse_args()
    preview_cleanup(delete=args.delete)