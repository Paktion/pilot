"""
Expression engine for ``abort_if`` + ``{{ var }}`` templating.

Backed by Jinja2 (already a daemon dep). We use a sandboxed environment with
no filesystem/template-loading capabilities — the only input is a small bag
of workflow variables plus a ``memory`` namespace the engine injects.

Supported filters: ``int``, ``float``, ``trim``, ``length``, plus whatever
Jinja ships by default. Function calls are disabled by the sandbox.
"""

from __future__ import annotations

from typing import Any

from jinja2 import StrictUndefined
from jinja2.exceptions import TemplateError
from jinja2.sandbox import ImmutableSandboxedEnvironment


class ExprError(ValueError):
    """Raised when an abort_if expression or a template fails to evaluate."""


class TemplateEngine:
    """Renders ``{{ var }}`` templates and evaluates abort_if predicates."""

    def __init__(self) -> None:
        self._env = ImmutableSandboxedEnvironment(
            undefined=StrictUndefined,
            autoescape=False,
        )
        self._env.filters["trim"] = lambda s: str(s).strip()

    def render(self, template: str, vars: dict[str, Any]) -> str:
        """Interpolate ``{{ var }}`` placeholders. Returns the rendered string."""
        try:
            return self._env.from_string(template).render(**vars)
        except TemplateError as exc:
            raise ExprError(f"template error in {template!r}: {exc}") from exc

    def evaluate_predicate(self, template: str, vars: dict[str, Any]) -> bool:
        """Evaluate an ``abort_if`` expression as a boolean.

        The template may be a plain predicate like ``{{ x > 5 }}`` or a raw
        expression wrapped in braces. The rendered result is coerced into a
        boolean: 'true', '1', 'yes' -> True; anything else -> False.
        """
        rendered = self.render(template, vars).strip().lower()
        return rendered in ("true", "1", "yes", "on")
