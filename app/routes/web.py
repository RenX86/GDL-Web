"""SPA static asset and index.html routes for the built Vite frontend."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response

from app.config import Settings
from app.security.path_guard import is_safe_path

_FALLBACK_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>GDL-Web</title>
</head>
<body>
  <main>
    <h1>GDL-Web Backend Running</h1>
    <p>
      Frontend bundle not found. Build the frontend in <code>frontend/</code>
      with <code>npm run build</code>.
    </p>
  </main>
</body>
</html>
"""


def build_web_router(settings: Settings) -> APIRouter:
    """Create router serving built Vite assets and SPA fallback."""
    router = APIRouter(include_in_schema=False)
    dist_dir = settings.frontend_dist_dir.resolve()
    assets_dir = dist_dir / "assets"

    def _serve_root_file(filename: str, cache_control: str) -> Response:
        candidate = dist_dir / filename
        if not is_safe_path(dist_dir, candidate) or candidate.is_symlink():
            raise HTTPException(status_code=404, detail="Not found.")
        if not candidate.exists() or not candidate.is_file():
            raise HTTPException(status_code=404, detail="Not found.")
        return FileResponse(
            path=candidate,
            headers={"Cache-Control": cache_control},
        )

    @router.get("/assets/{asset_path:path}")
    async def serve_asset(asset_path: str) -> FileResponse:
        if (
            not asset_path
            or asset_path.startswith(("/", "\\"))
            or "\x00" in asset_path
            or "\\" in asset_path
        ):
            raise HTTPException(status_code=404, detail="Asset not found.")

        parts = Path(asset_path).parts
        if any(part in ("", ".", "..") for part in parts):
            raise HTTPException(status_code=404, detail="Asset not found.")

        target = assets_dir / Path(*parts)
        if not is_safe_path(assets_dir, target) or target.is_symlink():
            raise HTTPException(status_code=404, detail="Asset not found.")
        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail="Asset not found.")

        return FileResponse(
            path=target,
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )

    @router.get("/favicon.ico")
    async def serve_favicon() -> Response:
        return _serve_root_file("favicon.ico", "public, max-age=86400")

    @router.get("/logo.png")
    async def serve_logo() -> Response:
        return _serve_root_file("logo.png", "public, max-age=86400")

    @router.get("/theme-init.js")
    async def serve_theme_init() -> Response:
        return _serve_root_file("theme-init.js", "no-cache")

    def _serve_index() -> Response:
        index_path = dist_dir / "index.html"
        if (
            is_safe_path(dist_dir, index_path)
            and not index_path.is_symlink()
            and index_path.is_file()
        ):
            return FileResponse(
                path=index_path,
                media_type="text/html; charset=utf-8",
                headers={"Cache-Control": "no-cache"},
            )
        return HTMLResponse(
            content=_FALLBACK_HTML,
            status_code=200,
            headers={"Cache-Control": "no-cache"},
        )

    @router.get("/")
    async def serve_spa_root() -> Response:
        return _serve_index()

    @router.get("/{full_path:path}")
    async def serve_spa_fallback(full_path: str) -> Response:
        # Never swallow unknown /api/* routes with index.html.
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API endpoint not found.")
        return _serve_index()

    return router
