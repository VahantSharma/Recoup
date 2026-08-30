"""'No card data' (docs/ENGINEERING-DOCTRINE.md) had zero dedicated test before an adversarial pass
(`docs/audit.md`) found it — real, but asserted only by the schema simply never having
grown a PAN/expiry/CVV column, never checked directly. Two structural checks, matching
the project's own precedent (tests/test_import_boundary.py,
tests/test_no_model_calls_in_reproducible_paths.py): walk the real SQLAlchemy model
metadata, and AST-walk the real prompt-building source, rather than trusting either by
convention.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from app import models

# Any SQLAlchemy model column whose name contains one of these (case-insensitive)
# would mean raw card data reached the database -- docs/ENGINEERING-DOCTRINE.md's "Never a PAN, expiry,
# or CVV, in the database or in a prompt." `card_id`/`card_number_invalid` (a decline
# REASON string, not a card number) below are the two real column/value names that
# legitimately contain "card" without being card data -- see the explicit exclusion.
_FORBIDDEN_NAME_FRAGMENTS = ("pan", "cvv", "cvc", "expiry", "expiration", "card_number", "cardnumber")


def _all_column_names() -> dict[str, list[str]]:
    """{model class name: [column names]} for every mapped model on Base.metadata --
    the real, live table definitions, not a hand-maintained list that could drift
    from them."""
    result: dict[str, list[str]] = {}
    for mapper in models.Base.registry.mappers:
        result[mapper.class_.__name__] = [c.name for c in mapper.columns]
    return result


def test_no_model_has_a_pan_expiry_or_cvv_column():
    offenders: dict[str, list[str]] = {}
    for cls_name, columns in _all_column_names().items():
        hits = [
            c for c in columns
            if any(fragment in c.lower() for fragment in _FORBIDDEN_NAME_FRAGMENTS)
        ]
        if hits:
            offenders[cls_name] = hits
    assert not offenders, (
        f"a model column name suggests raw card data: {offenders} -- docs/ENGINEERING-DOCTRINE.md requires "
        "tokenized references only (card_id), never a PAN, expiry, or CVV, in the database"
    )


def test_payment_case_only_carries_a_tokenized_card_reference():
    """The one column that legitimately has 'card' in its name -- confirmed here to be
    exactly the tokenized reference docs/ENGINEERING-DOCTRINE.md describes, not a proxy for something
    wider that might grow raw fields under it later."""
    columns = _all_column_names()["PaymentCase"]
    card_columns = [c for c in columns if "card" in c.lower()]
    assert card_columns == ["card_id"], (
        f"expected exactly one card-related column (the tokenized card_id) on "
        f"PaymentCase, found: {card_columns}"
    )


def test_the_check_actually_catches_a_forbidden_column_name():
    """Proves the fragment list isn't vacuous -- matching test_import_boundary.py's
    own precedent of proving a structural check can fail before trusting it passes."""
    hits = [c for c in ["card_id", "pan", "cvv_code", "card_expiry_month"] if any(
        fragment in c.lower() for fragment in _FORBIDDEN_NAME_FRAGMENTS
    )]
    assert hits == ["pan", "cvv_code", "card_expiry_month"]


# --- half two: the model's prompt-building code never touches card_id or
# error_description, structurally, not just "doesn't happen to reference them today" ---

_SYNTHESIS_PATH = Path(inspect.getfile(__import__("app.model.playbook_synthesis", fromlist=["x"])))

# Names that would mean a card-adjacent or free-text-narration field reached the
# synthesis prompt -- see app.models.PaymentCase's own docstring on why
# error_description is "the model's input, never a guardrail's": that's fine for the
# case-audit trace, but the SYNTHESIS prompt (unlike the case audit) is meant to carry
# only aggregate statistics, per its own module docstring -- "no raw narration, no
# synthesized customer text, no invented numbers."
_FORBIDDEN_IDENTIFIERS = {"card_id", "error_description", "error_code", "error_reason", "razorpay_payment_id"}


def _referenced_names(source: str) -> set[str]:
    tree = ast.parse(source, filename=str(_SYNTHESIS_PATH))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            names.add(node.value)
    return names


def test_synthesis_prompt_builder_never_references_card_or_narration_fields():
    source = _SYNTHESIS_PATH.read_text(encoding="utf-8")
    referenced = _referenced_names(source)
    hits = _FORBIDDEN_IDENTIFIERS & referenced
    assert not hits, (
        f"app/model/playbook_synthesis.py references {hits} -- the synthesis prompt "
        "must only ever carry aggregate statistics computed from a real run, never "
        "per-case card or narration fields (docs/ENGINEERING-DOCTRINE.md's 'no card data... in a prompt', "
        "and the module's own docstring)"
    )


def test_the_ast_check_actually_catches_a_forbidden_reference():
    """Same proof-of-non-vacuity discipline as the column-name check above."""
    hostile_source = "def f(case):\n    return case.card_id\n"
    assert _referenced_names(hostile_source) & _FORBIDDEN_IDENTIFIERS == {"card_id"}
