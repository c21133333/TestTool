from __future__ import annotations

# Import model modules so SQLAlchemy metadata is fully populated before migrations run.
from backend.app.models import access_token  # noqa: F401
from backend.app.models import api_case  # noqa: F401
from backend.app.models import audit_log  # noqa: F401
from backend.app.models import environment  # noqa: F401
from backend.app.models import execution  # noqa: F401
from backend.app.models import project  # noqa: F401
from backend.app.models import report  # noqa: F401
from backend.app.models import suite  # noqa: F401
from backend.app.models import user  # noqa: F401


def load_model_metadata() -> None:
    """Import side effects populate SQLAlchemy metadata for app startup and Alembic."""
