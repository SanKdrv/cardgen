"""Веб-форма для контент-менеджера."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from ....application.pipeline import CardGenerator
from ....application.ports import LLMProvider
from ....core.errors import CardgenError
from ....domain.models import GenerateOptions, ProductInput
from ..dependencies import get_generator, get_provider, get_templates
from ..examples import load_examples

router = APIRouter(include_in_schema=False)


def _context(provider: LLMProvider, **extra: Any) -> dict[str, Any]:
    return {
        "examples": load_examples(),
        "provider": provider.name,
        "provider_ready": provider.ready,
        "model": provider.model,
        **extra,
    }


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    provider: Annotated[LLMProvider, Depends(get_provider)],
    example: int | None = None,
) -> HTMLResponse:
    examples = load_examples()
    form: dict[str, Any] | None = None
    if example is not None and 0 <= example < len(examples):
        selected = examples[example]
        form = {
            "name": selected.get("name", ""),
            "manufacturer": selected.get("manufacturer", ""),
            "category": selected.get("category", ""),
            "description": selected.get("description", ""),
            "specs": [
                {"key": key, "value": value}
                for key, value in dict(selected.get("specs", {})).items()
            ],
            "allow_fallback": True,
        }
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context=_context(provider, error=None, form=form),
    )


@router.post("/ui/generate", response_class=HTMLResponse)
async def generate_from_form(
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    generator: Annotated[CardGenerator, Depends(get_generator)],
    provider: Annotated[LLMProvider, Depends(get_provider)],
) -> HTMLResponse:
    form = await request.form()
    spec_keys = [str(item) for item in form.getlist("spec_key")]
    spec_values = [str(item) for item in form.getlist("spec_value")]
    specs = {
        key.strip(): value.strip()
        for key, value in zip(spec_keys, spec_values, strict=False)
        if key.strip() and value.strip()
    }
    raw_form: dict[str, Any] = {
        "name": str(form.get("name", "")),
        "manufacturer": str(form.get("manufacturer", "")),
        "category": str(form.get("category", "")),
        "description": str(form.get("description", "")),
        "specs": [
            {"key": key, "value": value}
            for key, value in zip(spec_keys, spec_values, strict=False)
            if key.strip() or value.strip()
        ],
        "allow_fallback": form.get("allow_fallback") is not None,
    }

    try:
        product = ProductInput(
            name=raw_form["name"],
            manufacturer=raw_form["manufacturer"],
            category=raw_form["category"] or None,
            specs=specs,
            description=raw_form["description"],
        )
    except ValidationError as exc:
        message = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()[:3]
        )
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context=_context(
                provider,
                error=f"Проверьте форму: {message}",
                form=raw_form,
            ),
            status_code=422,
        )

    try:
        result = await generator.generate(
            product,
            GenerateOptions(allow_fallback=bool(raw_form["allow_fallback"])),
        )
    except CardgenError as exc:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context=_context(
                provider,
                error=getattr(exc, "message", str(exc)),
                form=raw_form,
            ),
            status_code=502,
        )

    return templates.TemplateResponse(
        request=request,
        name="result.html",
        context=_context(
            provider,
            result=result,
            json_text=result.model_dump_json(indent=2, exclude_none=True),
            markdown_text=result.markdown,
        ),
    )
