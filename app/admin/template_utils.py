"""Template utilities for admin UI."""

from datetime import datetime
from pathlib import Path

from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

# Cache the templates instance module-level to avoid recreating it
_env = None


def datetime_filter(value: datetime | None, format_str: str = "%Y-%m-%d %H:%M") -> str:
    """Format a datetime object as a string."""
    if value is None:
        return "-"
    return value.strftime(format_str)


def get_admin_env():
    """Get the admin Jinja2 environment."""
    global _env
    if _env is None:
        admin_path = Path(__file__).parent
        templates_dir = admin_path / "templates"
        loader = FileSystemLoader(str(templates_dir))
        # Disable caching to avoid Jinja2 LRUCache issues
        _env = Environment(
            loader=loader, autoescape=select_autoescape(["html", "xml"]), cache_size=0
        )
        # Add custom filters
        _env.filters["datetime"] = datetime_filter
    return _env


def render_template(template_name: str, **context) -> HTMLResponse:
    """Render a template and return HTMLResponse."""
    env = get_admin_env()
    template = env.get_template(template_name)
    html_content = template.render(**context)
    return HTMLResponse(content=html_content, status_code=200)


def render_template_with_status(
    template_name: str, status_code: int = 200, **context
) -> HTMLResponse:
    """Render a template with custom status code and return HTMLResponse."""
    env = get_admin_env()
    template = env.get_template(template_name)
    html_content = template.render(**context)
    return HTMLResponse(content=html_content, status_code=status_code)


__all__ = ["get_admin_env", "render_template", "render_template_with_status"]
