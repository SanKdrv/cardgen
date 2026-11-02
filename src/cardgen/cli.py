"""Командный интерфейс cardgen."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from . import __version__
from .config import Settings
from .errors import CardgenError
from .llm import build_provider
from .models import CardResult, GenerateOptions, ProductInput
from .pipeline import CardGenerator

logger = logging.getLogger(__name__)

_TRANSLIT = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


def slugify(value: str) -> str:
    translated = "".join(_TRANSLIT.get(char, char) for char in value.lower())
    slug = re.sub(r"[^a-z0-9]+", "-", translated).strip("-")
    return (slug[:60].rstrip("-")) or "product"


def _load_products(path: Path) -> list[ProductInput]:
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"не удалось прочитать {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} — некорректный JSON: {exc}") from exc

    if isinstance(raw, dict) and "products" in raw:
        items = raw["products"]
    elif isinstance(raw, dict) and "product" in raw:
        items = [raw["product"]]
    elif isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = [raw]
    else:
        raise ValueError("ожидался объект товара, массив товаров или ключ products")

    if not isinstance(items, list) or not items:
        raise ValueError("на входе нет ни одного товара")

    products: list[ProductInput] = []
    for index, item in enumerate(items, start=1):
        try:
            products.append(ProductInput.model_validate(item))
        except ValidationError as exc:
            details = "; ".join(
                f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                for error in exc.errors()[:3]
            )
            raise ValueError(f"товар #{index} не прошёл валидацию: {details}") from exc
    return products


def _parse_specs(values: list[str]) -> dict[str, str]:
    specs: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"характеристика «{value}» должна иметь вид 'название=значение'")
        key, spec_value = value.split("=", 1)
        if not key.strip() or not spec_value.strip():
            raise ValueError(f"характеристика «{value}» содержит пустое название или значение")
        specs[key.strip()] = spec_value.strip()
    return specs


def _products_from_args(args: argparse.Namespace) -> list[ProductInput]:
    if args.input:
        return _load_products(Path(args.input))
    if not args.name or not args.manufacturer:
        raise ValueError("укажите --input или пару --name и --manufacturer")
    return [
        ProductInput(
            name=args.name,
            manufacturer=args.manufacturer,
            category=args.category,
            specs=_parse_specs(args.spec or []),
            description=args.description or "",
        )
    ]


def _write_result(result: CardResult, directory: Path, index: int, overwrite: bool) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"{index:02d}-{slugify(result.product.name)}"
    paths = [
        directory / f"{stem}.json",
        directory / f"{stem}.md",
    ]
    if not overwrite:
        existing = [path for path in paths if path.exists()]
        if existing:
            raise FileExistsError(
                f"файлы уже существуют: {', '.join(str(path) for path in existing)}. "
                "Добавьте --overwrite, чтобы перезаписать."
            )
    paths[0].write_text(
        result.model_dump_json(indent=2, exclude_none=True) + "\n", encoding="utf-8"
    )
    paths[1].write_text(result.markdown, encoding="utf-8")
    return paths


def _print_summary(result: CardResult) -> None:
    status = "fallback" if result.meta.fallback_used else f"LLM×{result.meta.attempts}"
    missing = len(result.missing_fields)
    print(f"• {result.product.name}")
    print(f"  заголовок ({len(result.draft.seo_title)}): {result.draft.seo_title}")
    print(
        f"  описание: {len(result.draft.seo_description)} символов · "
        f"запросов: {len(result.draft.search_queries)} · пропусков: {missing} · {status}"
    )


async def _generate(args: argparse.Namespace) -> int:
    settings = Settings()
    if args.provider:
        settings = settings.model_copy(update={"provider": args.provider})
    if args.model:
        settings = settings.model_copy(update={"model": args.model})

    try:
        products = _products_from_args(args)
    except ValueError as exc:
        print(f"Ошибка входа: {exc}", file=sys.stderr)
        return 2

    provider = build_provider(settings)
    generator = CardGenerator(provider, settings)
    options = GenerateOptions(allow_fallback=not args.no_fallback)
    output = Path(args.output)
    results: list[CardResult] = []
    failed = 0

    try:
        for index, product in enumerate(products, start=1):
            try:
                result = await generator.generate(product, options)
            except CardgenError as exc:
                failed += 1
                print(f"✗ {product.name}: {getattr(exc, 'message', exc)}", file=sys.stderr)
                continue
            results.append(result)
            _print_summary(result)
            try:
                paths = _write_result(result, output, index, args.overwrite)
            except OSError as exc:
                print(f"Не удалось сохранить результат: {exc}", file=sys.stderr)
                return 2
            for path in paths:
                print(f"  → {path}")
    finally:
        await provider.aclose()

    if failed and not results:
        return 1
    print(f"\nГотово: {len(results)} из {len(products)}.")
    return 0


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    if args.provider:
        os.environ["CARDGEN_PROVIDER"] = args.provider
    if args.model:
        os.environ["CARDGEN_MODEL"] = args.model
    uvicorn.run(
        "cardgen.api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
    return 0


def _check_config(_args: argparse.Namespace) -> int:
    settings = Settings()
    provider = build_provider(settings)
    print(f"cardgen {__version__}")
    print(f"провайдер:   {provider.name}")
    print(f"модель:      {provider.model}")
    if provider.name == "openai":
        print(f"base_url:    {settings.base_url}")
        print(f"ключ:        {'задан' if settings.api_key_value else 'НЕ ЗАДАН'}")
        print(f"готовность:  {'да' if provider.ready else 'нет (будет использован шаблон)'}")
    else:
        print("готовность:  да (сеть не нужна)")
    return 0 if provider.ready else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cardgen",
        description="Генератор черновиков B2B-карточек контрольно-измерительных приборов.",
    )
    parser.add_argument("--version", action="version", version=f"cardgen {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser(
        "generate", help="сгенерировать карточки из JSON или аргументов"
    )
    generate.add_argument(
        "-i", "--input", help="JSON с товаром, массивом товаров или ключом products"
    )
    generate.add_argument("-o", "--output", default="artifacts", help="каталог для JSON и Markdown")
    generate.add_argument(
        "--overwrite", action="store_true", help="перезаписывать существующие файлы"
    )
    generate.add_argument("--provider", choices=["openai", "fixture", "template"])
    generate.add_argument("--model")
    generate.add_argument(
        "--no-fallback", action="store_true", help="не подменять результат шаблоном"
    )
    generate.add_argument("--name")
    generate.add_argument("--manufacturer")
    generate.add_argument("--category")
    generate.add_argument("--description")
    generate.add_argument(
        "--spec",
        action="append",
        metavar="КЛЮЧ=ЗНАЧЕНИЕ",
        help="характеристика; можно указывать несколько раз",
    )
    generate.set_defaults(handler=_generate)

    serve = subparsers.add_parser("serve", help="запустить веб-сервис")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    serve.add_argument("--provider", choices=["openai", "fixture", "template"])
    serve.add_argument("--model")
    serve.set_defaults(handler=_serve)

    check = subparsers.add_parser("check-config", help="показать конфигурацию и готовность")
    check.set_defaults(handler=_check_config)
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = args.handler
    if asyncio.iscoroutinefunction(handler):
        return int(asyncio.run(handler(args)))
    return int(handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
