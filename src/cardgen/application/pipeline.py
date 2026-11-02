"""Оркестрация: LLM → разбор → автопроверка → ретрай → безопасный шаблон."""

from __future__ import annotations

import asyncio
import logging
import time

from ..core.errors import (
    ConcurrencyLimitError,
    DraftParseError,
    LLMError,
    ValidationFailedError,
)
from ..domain.facts import build_facts, detect_missing_fields
from ..domain.guard import check_draft, summarize_violations
from ..domain.models import (
    CardMeta,
    CardResult,
    GenerateOptions,
    GuardReport,
    GuardViolation,
    ProductInput,
)
from .fallback import build_template_draft
from .parsing import parse_draft
from .ports import LLMProvider, PipelineSettings
from .prompts import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_correction_prompt,
    build_user_prompt,
)
from .render import to_markdown

logger = logging.getLogger(__name__)


class CardGenerator:
    """Генерирует карточку и снижает риск выдуманных фактов детерминированной проверкой."""

    def __init__(self, provider: LLMProvider, settings: PipelineSettings) -> None:
        self.provider = provider
        self.settings = settings
        self._semaphore = asyncio.Semaphore(settings.max_concurrency)

    async def generate(
        self,
        product: ProductInput,
        options: GenerateOptions | None = None,
    ) -> CardResult:
        """Ограничивает число одновременных генераций на процесс."""
        try:
            async with asyncio.timeout(self.settings.concurrency_timeout_s):
                async with self._semaphore:
                    return await self._generate_unchecked(product, options)
        except TimeoutError as exc:
            raise ConcurrencyLimitError(
                "сервис занят: превышен лимит одновременных генераций",
                self.settings.concurrency_timeout_s,
            ) from exc

    async def _generate_unchecked(
        self,
        product: ProductInput,
        options: GenerateOptions | None = None,
    ) -> CardResult:
        options = options or GenerateOptions()
        started = time.perf_counter()
        facts = build_facts(product)
        missing = detect_missing_fields(product)
        warnings: list[str] = []

        draft = None
        report: GuardReport | None = None
        attempts = 0
        fallback_reason: str | None = None

        if self.provider.name == "template":
            fallback_reason = "template_mode"
            warnings.append("Включён режим без LLM: карточка собрана детерминированным шаблоном.")
        else:
            base_prompt = build_user_prompt(product, missing)
            prompt = base_prompt
            last_violations: list[GuardViolation] = []

            try:
                for attempt in range(1, self.settings.max_attempts + 1):
                    attempts = attempt
                    raw = await self.provider.complete(system=SYSTEM_PROMPT, user=prompt)

                    try:
                        candidate = parse_draft(raw)
                    except DraftParseError as exc:
                        candidate_report = GuardReport(
                            ok=False,
                            violations=[
                                GuardViolation(
                                    code="invalid_json",
                                    field="response",
                                    message=str(exc),
                                )
                            ],
                            stats={},
                        )
                    else:
                        candidate_report = check_draft(product, facts, candidate)

                    if candidate_report.ok:
                        draft = candidate
                        report = candidate_report
                        break

                    last_violations = candidate_report.violations
                    logger.info(
                        "Черновик не прошёл проверку (попытка %s/%s): %s",
                        attempt,
                        self.settings.max_attempts,
                        summarize_violations(candidate_report.violations, limit=3),
                    )
                    if attempt < self.settings.max_attempts:
                        prompt = build_correction_prompt(
                            base_prompt, raw, candidate_report.violations
                        )

                if draft is None:
                    if not options.allow_fallback:
                        raise ValidationFailedError(
                            "ответ модели не прошёл автопроверку", last_violations
                        )
                    fallback_reason = "validation_failed"
                    reasons = summarize_violations(last_violations, limit=3)
                    warnings.append(
                        "Модель не прошла автопроверку; обращений к LLM: "
                        f"{attempts}. Причины: {reasons}. Использован безопасный шаблон."
                    )
            except LLMError as exc:
                if not options.allow_fallback:
                    raise
                fallback_reason = f"llm_error:{type(exc).__name__}"
                warnings.append(f"LLM недоступна: {exc.message}")

        if draft is None or report is None:
            draft = build_template_draft(product, missing)
            report = check_draft(product, facts, draft)
            if not report.ok:  # pragma: no cover - страховка от регрессии шаблона
                logger.error(
                    "Шаблон не прошёл проверку: %s",
                    summarize_violations(report.violations, limit=10),
                )
                raise ValidationFailedError(
                    "безопасный шаблон не прошёл автопроверку", report.violations
                )

        latency_ms = int((time.perf_counter() - started) * 1000)
        meta = CardMeta(
            provider=self.provider.name,
            model=self.provider.model,
            attempts=attempts,
            fallback_used=fallback_reason is not None,
            fallback_reason=fallback_reason,
            latency_ms=latency_ms,
            prompt_version=PROMPT_VERSION,
            validation=report,
        )
        result = CardResult(
            product=product,
            draft=draft,
            missing_fields=missing,
            warnings=warnings,
            meta=meta,
        )
        return result.model_copy(update={"markdown": to_markdown(result)})
