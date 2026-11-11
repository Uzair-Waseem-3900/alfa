import asyncio

from celery import shared_task
from django.db import close_old_connections


@shared_task(ignore_result=True)
def run_agent_task(run_id: str) -> None:
    """Answer one chat message. Each task gets its own event loop, so the
    Gemini client is built inside it (see config.configs)."""
    from .services.runner import execute_run  # import here: keeps worker start light

    close_old_connections()
    try:
        asyncio.run(execute_run(run_id))
    finally:
        close_old_connections()
