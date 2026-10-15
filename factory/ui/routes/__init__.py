"""FastAPI route modules for Factory Studio UI."""

from factory.ui.routes.jobs import router as jobs_router
from factory.ui.routes.repos import router as repos_router
from factory.ui.routes.studio_chat import router as studio_chat_router
from factory.ui.routes.studio_preview import router as studio_preview_router
from factory.ui.routes.studio_pulls import router as studio_pulls_router
from factory.ui.routes.studio_rollback import router as studio_rollback_router

__all__ = [
    "jobs_router",
    "repos_router",
    "studio_chat_router",
    "studio_preview_router",
    "studio_pulls_router",
    "studio_rollback_router",
]
