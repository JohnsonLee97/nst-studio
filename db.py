import os
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv
from datetime import datetime, timezone

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(ENV_PATH)


def get_connection():
    return mysql.connector.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ["DB_PORT"]),
        database=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        connection_timeout=5,
    )

def save_generation(details):
    completed_at = datetime.fromisoformat(
        details["completed_at_utc"]
    )

    completed_at = completed_at.astimezone(
        timezone.utc
    ).replace(tzinfo=None)

    sql = """
        INSERT INTO generations (
            run_id,
            completed_at_utc,
            iterations,
            style_weight,
            content_weight,
            total_variation_weight,
            max_dimension,
            runtime_seconds
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """

    values = (
        details["run_id"],
        completed_at,
        details["iterations"],
        details["style_weight"],
        details["content_weight"],
        details["total_variation_weight"],
        details["max_dimension"],
        details["runtime_seconds"],
    )

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, values)

        connection.commit()

def get_generations():
    sql = """
        SELECT
            run_id,
            completed_at_utc,
            iterations,
            style_weight,
            runtime_seconds
        FROM generations
        ORDER BY completed_at_utc DESC
        LIMIT 50
    """

    with get_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(sql)
            return cursor.fetchall()

if __name__ == "__main__":
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM generations")
            result = cursor.fetchone()

            print("MySQL connection successful.")
            print("Saved generations:", result[0])