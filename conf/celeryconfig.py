BROKER_HOST = "localhost"
BROKER_PORT = 5672
# BROKER_USER = "myuser"
# BROKER_PASSWORD = "mypassword"
# BROKER_VHOST = "myvhost"

CELERY_RESULT_BACKEND = "database"
CELERY_RESULT_DBURI = "postgresql:///openlibrary"
OL_RESULT_DB_PARAMETERS = { "dbn" : "postgres",
                            "db" : "openlibrary"}


CELERY_IMPORTS = ("openlibrary.tasks", )

OL_CONFIG = "conf/openlibrary.yml"

from datetime import timedelta

CELERYBEAT_SCHEDULE = {
    "runs-every-30-seconds": {
        "task": "openlibrary.tasks.update_support_from_email",
        "schedule": timedelta(seconds=30),
    },
}
