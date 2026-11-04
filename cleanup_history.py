import argparse
import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from mysql.connector import Error as MySQLError
from redis.exceptions import RedisError
from rq.exceptions import NoSuchJobError
from rq.job import Job
from rq.serializers import JSONSerializer

from db import get_connection
from queue_setup import (
    generation_queue,
    generation_timeout,
    queue_wait_timeout,
    redis_connection,
)


PROJECT_FOLDER = Path(__file__).resolve().parent
UPLOAD_FOLDER = PROJECT_FOLDER / "uploads"
TERMINAL_STATUSES = {"finished", "failed", "stopped", "canceled"}


def parse_timestamp(value, allow_naive=False):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)

    if not isinstance(value, datetime):
        raise ValueError("Invalid timestamp.")

    if value.tzinfo is None:
        if not allow_naive:
            raise ValueError("Timestamp must include a timezone.")
        value = value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def validate_folder(folder, run_id):
    if folder is not None and (
        folder.parent.resolve() != UPLOAD_FOLDER.resolve()
        or folder.name != run_id
        or folder.is_symlink()
    ):
        raise ValueError("Unsafe upload folder path.")


def read_document(folder, filename, run_id):
    if folder is None:
        return None

    path = folder / filename

    if path.is_symlink():
        raise ValueError(f"{filename} is a symbolic link.")

    if not path.exists():
        return None

    with path.open(encoding="utf-8") as file:
        details = json.load(file)

    if not isinstance(details, dict) or details.get("run_id") != run_id:
        raise ValueError(f"Invalid run ID in {filename}.")

    return details


def inspect_run(run_id, folder, record, retention):
    validate_folder(folder, run_id)

    try:
        job = Job.fetch(
            run_id,
            connection=redis_connection,
            serializer=JSONSerializer,
        )
    except NoSuchJobError:
        job = None

    if job is not None:
        if job.origin != generation_queue.name:
            raise ValueError("Job belongs to a different queue.")

        # Unknown states are preserved too. Never assume they are inactive.
        if job.get_status(refresh=True) not in TERMINAL_STATUSES:
            return None, "active"

    completion_times = []

    if record is not None:
        completion_times.append(
            parse_timestamp(record["completed_at_utc"], allow_naive=True)
        )

    metadata = read_document(folder, "metadata.json", run_id)

    if metadata is not None:
        completion_times.append(
            parse_timestamp(metadata["completed_at_utc"])
        )

    if completion_times:
        return max(completion_times) + retention, "completed"

    request_details = read_document(folder, "request.json", run_id)

    if request_details is None:
        raise ValueError("No completion or submission timestamp available.")

    submitted_at = parse_timestamp(request_details["submitted_at_utc"])
    reference_time = submitted_at

    if job is not None and job.ended_at is not None:
        reference_time = max(reference_time, parse_timestamp(job.ended_at))

    # If Redis has lost/expired a job, preserve its files for at least
    # the configured maximum queue wait plus execution time.
    submission_guard = submitted_at + timedelta(
        seconds=queue_wait_timeout + generation_timeout
    )

    expires_at = max(reference_time + retention, submission_guard)
    return expires_at, "unfinished"


def delete_expired_run(run_id, folder, retention):
    with get_connection() as connection:
        try:
            with connection.cursor(dictionary=True) as cursor:
                # Re-read the database and files just before deletion.
                cursor.execute(
                    """
                    SELECT run_id, completed_at_utc
                    FROM generations
                    WHERE run_id = %s
                    FOR UPDATE
                    """,
                    (run_id,),
                )
                record = cursor.fetchone()
                expires_at, _ = inspect_run(run_id, folder, record, retention)

                if expires_at is None or expires_at > datetime.now(timezone.utc):
                    connection.rollback()
                    return False

                if record is not None:
                    cursor.execute(
                        "DELETE FROM generations WHERE run_id = %s",
                        (run_id,),
                    )

                if folder is not None and folder.exists():
                    shutil.rmtree(folder)

            connection.commit()
            return True
        except Exception:
            connection.rollback()
            raise


def cleanup(delete=False):
    retention_hours = int(os.environ["IMAGE_RETENTION_HOURS"])

    if retention_hours <= 0:
        raise ValueError("IMAGE_RETENTION_HOURS must be greater than zero.")

    retention = timedelta(hours=retention_hours)
    now = datetime.now(timezone.utc)

    # Abort before touching data if job status cannot be checked.
    redis_connection.ping()

    if UPLOAD_FOLDER.is_symlink():
        raise ValueError("Uploads directory must not be a symbolic link.")

    with get_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT run_id, completed_at_utc FROM generations")
            database_records = {
                record["run_id"]: record for record in cursor.fetchall()
            }

            if delete:
                cursor.execute("DELETE FROM generations WHERE 1 = 0")
                connection.rollback()

    folders = {}

    if UPLOAD_FOLDER.exists():
        for folder in UPLOAD_FOLDER.iterdir():
            if not folder.is_symlink() and folder.is_dir():
                try:
                    if UUID(folder.name).hex == folder.name:
                        folders[folder.name] = folder
                except ValueError:
                    continue

    counts = {"expired": 0, "active": 0, "skipped": 0, "deleted": 0, "failed": 0}
    print(f"Retention: {retention_hours} hours")
    print(f"Checked at UTC: {now.isoformat()}")
    print()

    for run_id in sorted(set(database_records) | set(folders)):
        folder = folders.get(run_id)
        record = database_records.get(run_id)

        try:
            if UUID(run_id).hex != run_id:
                raise ValueError("Invalid run ID.")

            expires_at, kind = inspect_run(run_id, folder, record, retention)

            if expires_at is None:
                counts["active"] += 1
                continue

            if expires_at > now:
                continue

            counts["expired"] += 1
            print(f"EXPIRED {run_id} ({kind})")
            print(f"  Upload folder: {'yes' if folder is not None else 'no'}")
            print(f"  Database record: {'yes' if record is not None else 'no'}")

            if delete:
                if delete_expired_run(run_id, folder, retention):
                    counts["deleted"] += 1
                    print("  DELETED")
                else:
                    counts["skipped"] += 1
                    print("  SKIPPED: run changed or is active.")

        except RedisError:
            # Do not continue deleting if Redis becomes unavailable mid-run.
            raise
        except (OSError, KeyError, TypeError, ValueError, OverflowError, MySQLError) as error:
            if delete:
                counts["failed"] += 1
            else:
                counts["skipped"] += 1
            print(f"SKIPPED/FAILED {run_id}: {error}")

    print()
    print(f"Expired runs: {counts['expired']}")
    print(f"Active jobs preserved: {counts['active']}")
    print(f"Skipped runs needing review: {counts['skipped']}")

    if delete:
        print(f"Deleted runs: {counts['deleted']}")
        print(f"Failed deletions: {counts['failed']}")
    else:
        print("Preview only. No files or database records were deleted.")

    return 1 if counts["failed"] or counts["skipped"] else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Preview or delete expired generation uploads and history."
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Permanently delete eligible expired upload folders and records.",
    )
    args = parser.parse_args()

    try:
        raise SystemExit(cleanup(delete=args.delete))
    except (RedisError, MySQLError, OSError, KeyError, ValueError, OverflowError) as error:
        print(f"Cleanup stopped: {error}")
        raise SystemExit(1)
