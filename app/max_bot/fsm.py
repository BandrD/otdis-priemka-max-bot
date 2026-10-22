from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DialogState(str, Enum):
    TREE = "tree"
    WAIT_GIGACHAT = "wait_gigachat"


@dataclass
class UserSession:
    state: DialogState = DialogState.TREE
    node_id: str = "Q0"
    extra: dict[str, Any] = field(default_factory=dict)


class SessionStore:
    def __init__(self, root_id: str = "Q0") -> None:
        self.root_id = root_id
        self._data: dict[int, UserSession] = {}

    def get(self, chat_id: int) -> UserSession:
        if chat_id not in self._data:
            self._data[chat_id] = UserSession(node_id=self.root_id)
        return self._data[chat_id]

    def reset(self, chat_id: int) -> UserSession:
        self._data[chat_id] = UserSession(node_id=self.root_id)
        return self._data[chat_id]
