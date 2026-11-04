import os
from pathlib import Path

from dotenv import load_dotenv
from redis import Redis
from redis.exceptions import WatchError
from rq import Queue
from rq.exceptions import NoSuchJobError
from rq.job import Job
from rq.serializers import JSONSerializer


ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(ENV_PATH)


def positive_integer(name):
    value = int(os.environ[name])

    if value <= 0:
        raise ValueError(f"{name} must be greater than zero.")

    return value


generation_timeout = positive_integer(
    "GENERATION_TIMEOUT_SECONDS"
)

max_queued_jobs = positive_integer(
    "MAX_QUEUED_JOBS"
)

queue_wait_timeout = positive_integer(
    "QUEUE_WAIT_TIMEOUT_SECONDS"
)

result_retention_seconds = (
    positive_integer("IMAGE_RETENTION_HOURS") * 60 * 60
)

redis_connection = Redis.from_url(os.environ["REDIS_URL"])

generation_queue = Queue(
    name=os.environ["RQ_QUEUE_NAME"],
    connection=redis_connection,
    default_timeout=generation_timeout,
    serializer=JSONSerializer,
)


class GenerationQueueFull(Exception):
    pass


class OwnerAlreadyGenerating(Exception):
    def __init__(self, job_id):
        self.job_id = job_id
        super().__init__(
            "This browser session already has an active generation."
        )


def enqueue_generation(run_id, owner_id, iterations, style_weight):
    owner_key = (
        f"nst:{generation_queue.name}:owner:{owner_id}:active"
    )

    active_statuses = {
        "queued",
        "started",
        "deferred",
        "scheduled",
        "ready_to_enqueue",
    }

    with redis_connection.pipeline() as pipeline:
        while True:
            try:
                pipeline.watch(
                    generation_queue.key,
                    owner_key,
                )

                existing_id = pipeline.get(owner_key)

                if existing_id is not None:
                    existing_id = existing_id.decode("utf-8")

                    try:
                        existing_job = Job.fetch(
                            existing_id,
                            connection=redis_connection,
                            serializer=JSONSerializer,
                        )

                        existing_status = existing_job.get_status()

                    except NoSuchJobError:
                        existing_status = None

                    if existing_status in active_statuses:
                        raise OwnerAlreadyGenerating(existing_id)

                waiting_count = pipeline.llen(
                    generation_queue.key
                )

                if waiting_count >= max_queued_jobs:
                    raise GenerationQueueFull(
                        "The generation queue is full."
                    )

                job = generation_queue.create_job(
                    func="tasks.generate_image_job",
                    args=(
                        run_id,
                        owner_id,
                        iterations,
                        style_weight,
                    ),
                    job_id=run_id,
                    timeout=generation_timeout,
                    ttl=queue_wait_timeout,
                    result_ttl=result_retention_seconds,
                    failure_ttl=result_retention_seconds,
                    meta={
                        "owner_id": owner_id,
                        "run_id": run_id,
                    },
                )

                pipeline.multi()

                generation_queue.enqueue_job(
                    job,
                    pipeline=pipeline,
                )

                pipeline.set(
                    owner_key,
                    job.id,
                    ex=queue_wait_timeout + generation_timeout,
                )

                pipeline.execute()
                return job

            except WatchError:
                continue