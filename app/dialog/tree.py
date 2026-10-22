from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ChildRef:
    label: str
    target: str


@dataclass
class Payload:
    type: str  # text | link | gigachat
    text: str = ""
    url: str | None = None
    status: str | None = None


@dataclass
class Node:
    id: str
    title: str
    parent: str | None
    text: str
    children: list[ChildRef]
    payload: Payload | None


@dataclass
class NodeView:
    node: Node
    body: str
    keyboard_children: list[ChildRef]
    show_back: bool
    show_home: bool
    await_gigachat: bool


class DialogTree:
    def __init__(self, root_id: str, nodes: dict[str, Node], faq_url: str, site_url: str) -> None:
        self.root_id = root_id
        self.nodes = nodes
        self.faq_url = faq_url
        self.site_url = site_url

    def get(self, node_id: str) -> Node:
        if node_id not in self.nodes:
            raise KeyError(node_id)
        return self.nodes[node_id]

    def parent_of(self, node_id: str) -> str | None:
        return self.get(node_id).parent

    def view(self, node_id: str) -> NodeView:
        node = self.get(node_id)
        await_giga = False
        parts: list[str] = [f"**{node.title}**"]
        if node.text:
            parts.append("")
            parts.append(node.text)

        if node.payload:
            p = node.payload
            if p.type == "text":
                parts.append("")
                parts.append(p.text)
                if p.status == "needs_content":
                    parts.append("")
                    parts.append(f"_Актуальные данные: {self.faq_url}_")
            elif p.type == "link":
                parts.append("")
                parts.append(p.text)
                if p.url:
                    parts.append(p.url)
            elif p.type == "gigachat":
                parts.append("")
                parts.append(p.text)
                await_giga = True

        if node.children:
            parts.append("")
            parts.append("Выберите пункт:")

        return NodeView(
            node=node,
            body="\n".join(parts).strip(),
            keyboard_children=list(node.children),
            show_back=node.parent is not None,
            show_home=node.id != self.root_id,
            await_gigachat=await_giga,
        )


def load_dialog_tree(path: Path) -> DialogTree:
    raw = json.loads(path.read_text(encoding="utf-8"))
    nodes: dict[str, Node] = {}
    for nid, n in (raw.get("nodes") or {}).items():
        children = [
            ChildRef(label=c["label"], target=c["target"]) for c in (n.get("children") or [])
        ]
        payload = None
        if n.get("payload"):
            pl = n["payload"]
            payload = Payload(
                type=pl["type"],
                text=str(pl.get("text") or ""),
                url=pl.get("url"),
                status=pl.get("status"),
            )
        nodes[nid] = Node(
            id=n["id"],
            title=n.get("title") or nid,
            parent=n.get("parent"),
            text=str(n.get("text") or ""),
            children=children,
            payload=payload,
        )
    root = raw.get("root_id") or "Q0"
    if root not in nodes:
        raise ValueError(f"root {root} missing")
    return DialogTree(
        root_id=root,
        nodes=nodes,
        faq_url=str(raw.get("faq_url") or ""),
        site_url=str(raw.get("site_url") or ""),
    )
