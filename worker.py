from rq import Worker
from rq.serializers import JSONSerializer

from queue_setup import generation_queue, redis_connection


if __name__ == "__main__":
    worker = Worker(
        [generation_queue],
        connection=redis_connection,
        serializer=JSONSerializer,
    )

    worker.work()