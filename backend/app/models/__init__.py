"""Import every model so Base.metadata knows all tables (used by Alembic)."""

from app.models import app as app_models  # noqa: F401
from app.models import mcp as mcp_models  # noqa: F401
