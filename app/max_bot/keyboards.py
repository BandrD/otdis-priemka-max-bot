from __future__ import annotations

from typing import Any

from app.dialog.tree import NodeView


def _rows(buttons: list[dict[str, Any]], per_row: int = 1) -> list[list[dict[str, Any]]]:
    return [buttons[i : i + per_row] for i in range(0, len(buttons), per_row)]


def node_keyboard(view: NodeView) -> dict[str, Any]:
    buttons: list[dict[str, Any]] = [
        {"type": "callback", "text": c.label[:64], "payload": f"go:{c.target}"}
        for c in view.keyboard_children
    ]
    nav: list[dict[str, Any]] = []
    if view.show_back:
        nav.append({"type": "callback", "text": "◀ Назад", "payload": "nav:back"})
    if view.show_home:
        nav.append({"type": "callback", "text": "В начало", "payload": "nav:home"})
    rows = _rows(buttons, 1)
    if nav:
        rows.append(nav)
    return {"type": "inline_keyboard", "payload": {"buttons": rows or [nav]}}


def cancel_giga_menu() -> dict[str, Any]:
    return {
        "type": "inline_keyboard",
        "payload": {
            "buttons": [
                [
                    {"type": "callback", "text": "◀ Назад", "payload": "nav:back"},
                    {"type": "callback", "text": "В начало", "payload": "nav:home"},
                ]
            ]
        },
    }
