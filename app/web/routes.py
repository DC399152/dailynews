from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=Path(__file__).parents[1] / "templates")


@router.get("/")
def dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="dashboard.html")


@router.get("/runs/{run_id}/view")
def run_detail(request: Request, run_id: str):
    return templates.TemplateResponse(
        request=request,
        name="run_detail.html",
        context={"run_id": run_id},
    )


@router.get("/digests/{digest_id}/view")
def digest_detail(request: Request, digest_id: str):
    return templates.TemplateResponse(
        request=request,
        name="digest_detail.html",
        context={"digest_id": digest_id},
    )
