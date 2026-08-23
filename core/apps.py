import os

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self) -> None:
        import core.signals.handlers  # noqa: F401

        from storefront import container_metrics

        # Container metrics describe the whole container, not one worker, so
        # exactly one of gunicorn's 3 workers may emit them — otherwise all
        # three push identical series and the backend sees conflicting
        # datapoints for the same timestamp. O_CREAT|O_EXCL is the cheapest
        # cross-process election available without adding a coordination
        # dependency; the lock lives in the container's own tmpfs, so a
        # redeploy always starts clean.
        if container_metrics.available():
            try:
                os.close(os.open('/tmp/container-metrics.lock',
                                 os.O_CREAT | os.O_EXCL))
            except FileExistsError:
                pass
            else:
                container_metrics.register()
