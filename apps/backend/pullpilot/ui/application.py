"""FastAPI wiring helpers for the Pullpilot UI."""
from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from typing import Any, Mapping, Optional

from ..auth import TOKEN_ENV
from ..resources import get_resource_path


def configure_application(app: Any, api: Any) -> None:
    """Configure FastAPI routes and assets for the UI."""

    from fastapi import Depends, HTTPException, Request
    from fastapi.responses import (
        FileResponse,
        HTMLResponse,
        JSONResponse,
        RedirectResponse,
        Response,
    )
    from fastapi.staticfiles import StaticFiles

    ui_root_dir = get_resource_path("ui")
    ui_dist_dir = ui_root_dir / "dist"
    dist_index_path = ui_dist_dir / "index.html"
    has_built_assets = dist_index_path.exists()

    backend_root = Path(__file__).resolve().parent.parent.parent
    apps_root = backend_root.parent
    ui_source_candidates = (
        apps_root / "frontend",
        backend_root / "ui",
    )
    ui_source_root = next((path for path in ui_source_candidates if path.exists()), ui_source_candidates[0])
    ui_source_index_path = ui_source_root / "index.html"
    ui_source_src_dir = ui_source_root / "src"
    ui_source_styles_path = ui_source_src_dir / "styles.css"
    ui_source_script_path = ui_source_src_dir / "app.js"

    use_source_assets = not has_built_assets and ui_source_index_path.exists()

    if has_built_assets:
        ui_index_path = dist_index_path
        ui_assets_dir = ui_dist_dir / "assets"
        ui_manifest_path = ui_dist_dir / "manifest.json"
    elif use_source_assets:
        ui_index_path = ui_source_index_path
        ui_assets_dir = None
        ui_manifest_path = None
    else:
        raise RuntimeError(
            "UI assets are missing; run 'npm run build' or install the source tree"
        )

    ui_index_content = ui_index_path.read_text(encoding="utf-8")
    ui_styles_path = ui_source_styles_path if ui_source_styles_path.exists() else None
    ui_script_path = ui_source_script_path if ui_source_script_path.exists() else None

    if ui_assets_dir and ui_assets_dir.exists():
        app.mount("/ui/assets", StaticFiles(directory=ui_assets_dir), name="ui-assets")

    if not has_built_assets and ui_source_src_dir.exists():
        app.mount("/ui/src", StaticFiles(directory=ui_source_src_dir), name="ui-src")

    if ui_manifest_path and ui_manifest_path.exists():
        @app.get("/ui/manifest.json")
        def get_ui_manifest() -> FileResponse:  # pragma: no cover - FastAPI runtime
            return FileResponse(ui_manifest_path, media_type="application/json")

    @app.get("/", include_in_schema=False)
    def redirect_root_to_ui() -> RedirectResponse:  # pragma: no cover - FastAPI runtime
        return RedirectResponse("/ui/", status_code=HTTPStatus.TEMPORARY_REDIRECT)

    @app.get("/ui", include_in_schema=False)
    def redirect_ui() -> RedirectResponse:  # pragma: no cover - FastAPI runtime
        return RedirectResponse("/ui/", status_code=HTTPStatus.TEMPORARY_REDIRECT)

    if ui_styles_path:
        @app.get("/ui/styles.css")
        def get_ui_styles() -> FileResponse:  # pragma: no cover - FastAPI runtime
            return FileResponse(ui_styles_path, media_type="text/css")

    if ui_script_path:
        @app.get("/ui/app.js")
        def get_ui_script() -> FileResponse:  # pragma: no cover - FastAPI runtime
            return FileResponse(ui_script_path, media_type="application/javascript")

    @app.get("/ui/", response_class=HTMLResponse)
    def get_ui_page() -> HTMLResponse:  # pragma: no cover - FastAPI runtime
        return HTMLResponse(ui_index_content)

    async def _require_auth(request: Request) -> None:
        authenticator = api.authenticator
        if not authenticator or not authenticator.configured:
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail={
                    "error": "missing credentials",
                    "details": f"Set the {TOKEN_ENV} environment variable and send an Authorization header.",
                },
            )
        if authenticator.authorize(request.headers):
            return
        raise HTTPException(status_code=HTTPStatus.UNAUTHORIZED, detail={"error": "unauthorized"})

    @app.get("/ui/config", dependencies=[Depends(_require_auth)])
    def get_ui_config(request: Request):  # pragma: no cover - FastAPI runtime
        status, body = api.handle_request("GET", "/ui/config", headers=request.headers)
        if status != HTTPStatus.OK:
            raise HTTPException(status_code=status, detail=body)
        return JSONResponse(body, status_code=status)

    @app.get("/ui/auth-check", dependencies=[Depends(_require_auth)])
    def get_ui_auth_check(request: Request):  # pragma: no cover - FastAPI runtime
        status, body = api.handle_request("GET", "/ui/auth-check", headers=request.headers)
        if status == HTTPStatus.NO_CONTENT:
            return Response(status_code=status)
        if status != HTTPStatus.OK:
            raise HTTPException(status_code=status, detail=body)
        return JSONResponse(body, status_code=status)

    @app.post("/ui/config", dependencies=[Depends(_require_auth)])
    async def post_ui_config(request: Request):  # pragma: no cover - FastAPI runtime
        payload = await request.json()
        status, body = api.handle_request(
            "POST", "/ui/config", payload, request.headers
        )
        if status != HTTPStatus.OK:
            raise HTTPException(status_code=status, detail=body)
        return JSONResponse(body, status_code=status)

    @app.get("/ui/logs", dependencies=[Depends(_require_auth)])
    def get_ui_logs(request: Request):  # pragma: no cover - FastAPI runtime
        name = request.query_params.get("name")
        payload = {"name": name} if name is not None else None
        status, body = api.handle_request(
            "GET", "/ui/logs", payload, request.headers
        )
        if status != HTTPStatus.OK:
            raise HTTPException(status_code=status, detail=body)
        return JSONResponse(body, status_code=status)

    @app.post("/ui/logs", dependencies=[Depends(_require_auth)])
    async def post_ui_logs(request: Request):  # pragma: no cover - FastAPI runtime
        payload = await request.json()
        status, body = api.handle_request(
            "POST", "/ui/logs", payload, request.headers
        )
        if status != HTTPStatus.OK:
            raise HTTPException(status_code=status, detail=body)
        return JSONResponse(body, status_code=status)

    @app.post("/ui/run-test", dependencies=[Depends(_require_auth)])
    async def post_ui_run_test(request: Request):  # pragma: no cover - FastAPI runtime
        status, body = api.handle_request("POST", "/ui/run-test", headers=request.headers)
        if status != HTTPStatus.OK:
            raise HTTPException(status_code=status, detail=body)
        return JSONResponse(body, status_code=status)

    @app.get("/config", dependencies=[Depends(_require_auth)])
    def get_config(request: Request):  # pragma: no cover - FastAPI runtime
        status, body = api.handle_request("GET", "/config", headers=request.headers)
        return JSONResponse(body, status_code=status)

    @app.put("/config", dependencies=[Depends(_require_auth)])
    async def put_config(request: Request):  # pragma: no cover - FastAPI runtime
        payload = await request.json()
        status, body = api.handle_request("PUT", "/config", payload, request.headers)
        if status != HTTPStatus.OK:
            raise HTTPException(status_code=status, detail=body)
        return JSONResponse(body)

    @app.get("/schedule", dependencies=[Depends(_require_auth)])
    def get_schedule(request: Request):  # pragma: no cover - FastAPI runtime
        status, body = api.handle_request("GET", "/schedule", headers=request.headers)
        if status != HTTPStatus.OK:
            raise HTTPException(status_code=status, detail=body)
        return JSONResponse(body, status_code=status)

    @app.put("/schedule", dependencies=[Depends(_require_auth)])
    async def put_schedule(request: Request):  # pragma: no cover - FastAPI runtime
        payload = await request.json()
        status, body = api.handle_request("PUT", "/schedule", payload, request.headers)
        if status != HTTPStatus.OK:
            raise HTTPException(status_code=status, detail=body)
        return JSONResponse(body)

    def handle_request(
        method: str,
        path: str,
        payload: Optional[Mapping[str, Any]] = None,
        headers: Optional[Mapping[str, str]] = None,
    ):
        return api.handle_request(method, path, payload, headers)

    setattr(app, "handle_request", handle_request)
