from __future__ import annotations

import logging
from typing import Any

from app.config import Settings
from app.dialog.tree import DialogTree, load_dialog_tree
from app.llm.gigachat_client import GigaChatClient
from app.llm.text_split import split_text
from app.max_bot.client import MaxClient
from app.max_bot.fsm import DialogState, SessionStore
from app.max_bot.keyboards import cancel_giga_menu, node_keyboard
from app.storage.store import Storage

logger = logging.getLogger(__name__)


def _chat_id_from_message(message: dict[str, Any]) -> int | None:
    recipient = message.get("recipient") or {}
    chat_id = recipient.get("chat_id")
    if chat_id is not None:
        return int(chat_id)
    sender = message.get("sender") or {}
    if sender.get("user_id") is not None:
        return int(sender["user_id"])
    return None


class BotApp:
    def __init__(
        self,
        settings: Settings,
        client: MaxClient,
        storage: Storage,
        gigachat: GigaChatClient | None,
        tree: DialogTree | None = None,
    ) -> None:
        self.settings = settings
        self.client = client
        self.storage = storage
        self.gigachat = gigachat
        self.tree = tree or load_dialog_tree(settings.dialog_tree_path)
        self.sessions = SessionStore(root_id=self.tree.root_id)
        self._bg: set[Any] = set()

    def _spawn(self, coro: Any) -> None:
        import asyncio

        task = asyncio.create_task(coro)
        self._bg.add(task)
        task.add_done_callback(self._bg.discard)

    async def send_chunks(
        self,
        chat_id: int,
        text: str,
        *,
        attachments: list | None = None,
    ) -> None:
        chunks = split_text(text)
        for i, chunk in enumerate(chunks):
            atts = attachments if i == 0 else None
            await self.client.send_message(
                chat_id=chat_id,
                text=chunk,
                format="markdown",
                attachments=atts,
            )

    async def show_node(self, chat_id: int, node_id: str) -> None:
        session = self.sessions.get(chat_id)
        session.node_id = node_id
        view = self.tree.view(node_id)
        if view.await_gigachat:
            session.state = DialogState.WAIT_GIGACHAT
            await self.send_chunks(
                chat_id,
                view.body,
                attachments=[cancel_giga_menu()],
            )
        else:
            session.state = DialogState.TREE
            await self.send_chunks(
                chat_id,
                view.body,
                attachments=[node_keyboard(view)],
            )

    async def send_welcome(self, chat_id: int) -> None:
        self.sessions.reset(chat_id)
        await self.show_node(chat_id, self.tree.root_id)

    async def handle_update(self, update: dict[str, Any]) -> None:
        utype = update.get("update_type")
        try:
            if utype == "bot_started":
                await self.send_welcome(int(update["chat_id"]))
            elif utype == "message_created":
                await self._on_message(update.get("message") or {})
            elif utype == "message_callback":
                await self._on_callback(update)
        except Exception:
            logger.exception("handle_update failed type=%s", utype)

    async def _on_callback(self, update: dict[str, Any]) -> None:
        callback = update.get("callback") or {}
        callback_id = callback.get("callback_id")
        payload = (callback.get("payload") or "").strip()
        message = update.get("message") or {}
        chat_id = _chat_id_from_message(message)
        if chat_id is None and update.get("chat_id") is not None:
            chat_id = int(update["chat_id"])
        if callback_id:
            try:
                await self.client.answer_callback(callback_id, notification="OK")
            except Exception:
                logger.exception("answer_callback failed")
        if chat_id is None:
            return

        session = self.sessions.get(chat_id)
        if payload == "nav:home":
            await self.send_welcome(chat_id)
            return
        if payload == "nav:back":
            parent = self.tree.parent_of(session.node_id)
            await self.show_node(chat_id, parent or self.tree.root_id)
            return
        if payload.startswith("go:"):
            target = payload.split(":", 1)[1]
            try:
                self.tree.get(target)
            except KeyError:
                await self.client.send_message(
                    chat_id=chat_id,
                    text="Пункт не найден. Вернитесь в начало.",
                    format="markdown",
                )
                await self.send_welcome(chat_id)
                return
            await self.show_node(chat_id, target)

    async def _on_message(self, message: dict[str, Any]) -> None:
        chat_id = _chat_id_from_message(message)
        if chat_id is None:
            return
        sender = message.get("sender") or {}
        if sender.get("is_bot"):
            return
        body = message.get("body") or {}
        text = (body.get("text") or "").strip()
        if not text:
            return

        if text in {"/start", "start", "меню", "Меню", "начало"}:
            await self.send_welcome(chat_id)
            return

        session = self.sessions.get(chat_id)
        if session.state == DialogState.WAIT_GIGACHAT:
            await self._answer_gigachat(chat_id, text)
            return

        # вне сценария без явного режима — предложить GigaChat / меню
        hint = (
            "Выберите пункт меню кнопками ниже.\n\n"
            "Или откройте **«Не нашли ответ?» → Задать вопрос GigaChat** "
            "для вопроса вне сценария."
        )
        await self.show_node(chat_id, session.node_id)
        await self.client.send_message(chat_id=chat_id, text=hint, format="markdown")

    async def _answer_gigachat(self, chat_id: int, text: str) -> None:
        session = self.sessions.get(chat_id)
        if self.gigachat is None or not self.gigachat.ready:
            await self.send_chunks(
                chat_id,
                (
                    "GigaChat сейчас выключен (нет ключа или `GIGACHAT_ENABLED=false`).\n\n"
                    f"База знаний: {self.tree.faq_url}"
                ),
                attachments=[cancel_giga_menu()],
            )
            return
        try:
            reply = await self.gigachat.ask(text)
            self.storage.log_token_usage(
                prompt_tokens=reply.prompt_tokens,
                completion_tokens=reply.completion_tokens,
                total_tokens=reply.total_tokens,
                note="off_scenario",
            )
            await self.send_chunks(
                chat_id,
                reply.text,
                attachments=[cancel_giga_menu()],
            )
        except Exception:
            logger.exception("GigaChat failed")
            await self.send_chunks(
                chat_id,
                f"Не удалось получить ответ GigaChat. Попробуйте позже или FAQ:\n{self.tree.faq_url}",
                attachments=[cancel_giga_menu()],
            )
        # остаёмся в WAIT_GIGACHAT для следующего вопроса; назад — через кнопки
        session.state = DialogState.WAIT_GIGACHAT
