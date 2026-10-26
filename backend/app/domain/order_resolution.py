"""Deterministic order-reference matching over an already-authorized candidate set."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

_WORD = re.compile(r"[a-z0-9]+")
_LEADING_FILLER = {"my", "the", "order", "item", "product", "please", "cancel", "just"}
_VAGUE_REFERENCES = {
    ("it",), ("that",), ("that", "one"), ("this",), ("this", "one"),
    ("that", "order"), ("same", "one"),
}


def _tokens(value: str) -> list[str]:
    tokens = _WORD.findall(value.casefold())
    while tokens and tokens[0] in _LEADING_FILLER:
        tokens.pop(0)
    if len(tokens) >= 2 and tokens[0] == "vit" and tokens[1] == "c":
        tokens[:2] = ["vitamin", "c"]
    return tokens


def _compact(tokens: list[str]) -> str:
    return "".join(tokens)


def _reference_result(status: str, **data: Any) -> dict[str, Any]:
    return {"ok": True, "match_status": status, **data}


def resolve_order_reference(
    reference: str,
    candidates: list[dict[str, Any]],
    conversation_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve only against orders the caller is authorized to see.

    A unique match returns the complete order. Ambiguous matches return only
    clarification fields; this function never selects one on a fuzzy tie.
    """
    query_tokens = _tokens(reference)
    if not query_tokens:
        return _reference_result("needs_clarification", matches=[])

    candidate_by_id = {
        _compact(_tokens(order.get("order_id", ""))): order
        for order in candidates
        if isinstance(order.get("order_id"), str)
    }
    query_compact = _compact(query_tokens)
    if len(query_compact) < 3:
        return _reference_result("needs_clarification", matches=[])

    if tuple(query_tokens) in _VAGUE_REFERENCES:
        last_order_id = (conversation_context or {}).get("last_order_id")
        contextual_key = _compact(_tokens(str(last_order_id))) if last_order_id else ""
        contextual_order = candidate_by_id.get(contextual_key)
        if contextual_order is None:
            return _reference_result("needs_clarification", matches=[])
        matches = [contextual_order]
    else:
        matches = []
        direct_id = query_compact
        if direct_id in candidate_by_id:
            matches = [candidate_by_id[direct_id]]
        else:
            for order in candidates:
                item_values = order.get("items", [])
                if not isinstance(item_values, list):
                    continue
                normalized_items = [
                    _compact(_tokens(item))
                    for item in item_values
                    if isinstance(item, str)
                ]
                if any(query_compact in item for item in normalized_items):
                    matches.append(order)

    # The same order can match more than one line item; count orders, not lines.
    unique_matches = {
        order["order_id"].upper(): order for order in matches
    }
    if not unique_matches:
        return _reference_result("not_found", matches=[])
    if len(unique_matches) > 1:
        summaries = [
            {
                "order_id": order["order_id"],
                "items": deepcopy(order.get("items", [])),
                "status": order.get("status"),
            }
            for order in sorted(unique_matches.values(), key=lambda item: item["order_id"])
        ]
        return _reference_result("ambiguous", matches=summaries)
    return _reference_result("matched", order=deepcopy(next(iter(unique_matches.values()))))
