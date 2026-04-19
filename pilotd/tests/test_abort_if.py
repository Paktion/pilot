"""TemplateEngine — {{ var }} rendering + abort_if predicate eval."""

from __future__ import annotations

import pytest

from pilot.workflow.expr import ExprError, TemplateEngine


def test_render_simple() -> None:
    eng = TemplateEngine()
    assert eng.render("Hello {{ name }}", {"name": "Pilot"}) == "Hello Pilot"


def test_predicate_true() -> None:
    eng = TemplateEngine()
    assert eng.evaluate_predicate("{{ x | int > 5 }}", {"x": "10"}) is True
    assert eng.evaluate_predicate("{{ x | int > 5 }}", {"x": "3"}) is False


def test_predicate_compound() -> None:
    eng = TemplateEngine()
    assert eng.evaluate_predicate(
        "{{ a > 5 and b < 10 }}",
        {"a": 6, "b": 3},
    ) is True


def test_predicate_nested_memory() -> None:
    eng = TemplateEngine()
    vars_ = {"bill": "12.50", "memory": {"median": 20.0}}
    assert eng.evaluate_predicate(
        "{{ bill | float > memory.median * 0.5 }}",
        vars_,
    ) is True


def test_missing_variable_raises() -> None:
    eng = TemplateEngine()
    with pytest.raises(ExprError):
        eng.evaluate_predicate("{{ missing > 1 }}", {})


def test_function_call_blocked_by_sandbox() -> None:
    eng = TemplateEngine()
    with pytest.raises(ExprError):
        eng.render("{{ __class__.mro() }}", {})
