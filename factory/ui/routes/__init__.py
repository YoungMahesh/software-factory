"""FastAPI route modules for Factory Studio UI."""

from factory.ui.routes.chat import router as chat_router
from factory.ui.routes.diffs import router as diffs_router
from factory.ui.routes.files import router as files_router
from factory.ui.routes.jobs import router as jobs_router
from factory.ui.routes.preview import router as preview_router
from factory.ui.routes.pulls import router as pulls_router
from factory.ui.routes.repos import router as repos_router
from factory.ui.routes.rollback import router as rollback_router
from factory.ui.routes.terminal import router as terminal_router

__all__ = [
    "chat_router",
    "diffs_router",
    "files_router",
    "jobs_router",
    "preview_router",
    "pulls_router",
    "repos_router",
    "rollback_router",
    "terminal_router",
]

