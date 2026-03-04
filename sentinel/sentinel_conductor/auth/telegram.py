"""
sentinel_conductor.auth.telegram
==================================
TelegramBotProvider — 2FA via Telegram Bot inline keyboard.

Flow
----
1. ``issue_challenge(context)``
   - Generates a UUID challenge_id.
   - Schedules ``_send_challenge_message()`` on the bot's dedicated event loop
     (running in a daemon thread).
   - Returns immediately with ``ChallengeResponse(status=PENDING)``.

2. Telegram user presses ✅ Approve or ❌ Reject button.
   - ``_on_callback_query()`` handler fires on the bot loop.
   - Updates ``self._results[challenge_id]`` to APPROVED or REJECTED.
   - Edits the original message to show the decision + approver name.

3. ``verify_challenge(challenge_id, external_ref)``
   - Thread-safe read of ``self._results``.
   - Called by ``_TwoFAPoller`` in the conductor every N seconds.

Configuration (oslo.config [telegram] group)
--------------------------------------------
  bot_token          — Telegram Bot API token from @BotFather
  approver_chat_id   — chat_id of the human approver (personal, group, or channel)
  polling_interval_seconds — how often the bot polls Telegram for updates

Getting your chat_id
--------------------
  1. Start a conversation with your bot.
  2. Send any message.
  3. Open: https://api.telegram.org/bot<TOKEN>/getUpdates
  4. Look for "chat": {"id": <YOUR_CHAT_ID>}
"""

import asyncio
import logging
import threading
import time
import uuid
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, ApplicationBuilder, CallbackQueryHandler, ContextTypes

from sentinel_conductor.auth.base import (
    BaseAuthProvider,
    ChallengeContext,
    ChallengeResponse,
    ChallengeStatus,
)

LOG = logging.getLogger(__name__)

_ACTION_APPROVE = "approve"
_ACTION_REJECT = "reject"


class TelegramBotProvider(BaseAuthProvider):
    """
    2FA provider that sends Telegram messages with Approve / Reject buttons.

    The bot runs in a dedicated daemon thread with its own asyncio event loop.
    All cross-thread communication uses ``asyncio.run_coroutine_threadsafe``
    and a plain dict guarded by a ``threading.Lock``.
    """

    name = "telegram"

    def __init__(
        self,
        bot_token: str,
        approver_chat_id: str,
        polling_interval_seconds: int = 5,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)

        if not bot_token:
            raise ValueError(
                "TelegramBotProvider requires [telegram] bot_token to be set."
            )
        if not approver_chat_id:
            raise ValueError(
                "TelegramBotProvider requires [telegram] approver_chat_id to be set."
            )

        self._bot_token = bot_token
        self._approver_chat_id = str(approver_chat_id)
        self._poll_interval = polling_interval_seconds

        # challenge_id → ChallengeStatus (written by bot thread, read by poller thread)
        self._results: dict[str, ChallengeStatus] = {}
        self._results_lock = threading.Lock()

        # Build the telegram Application (must be created before the event loop starts)
        self._app: Application = (
            ApplicationBuilder()
            .token(bot_token)
            .build()
        )
        self._app.add_handler(CallbackQueryHandler(self._on_callback_query))

        # Dedicated event loop + daemon thread for the bot
        self._bot_loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        self._bot_thread = threading.Thread(
            target=self._run_bot_thread,
            daemon=True,
            name="telegram-bot",
        )
        self._bot_thread.start()

        # Give the bot loop a moment to initialise before accepting challenges
        time.sleep(1.5)
        LOG.info(
            "TelegramBotProvider started: approver_chat_id=%s", self._approver_chat_id
        )

    # ------------------------------------------------------------------
    # Bot lifecycle (runs in daemon thread)
    # ------------------------------------------------------------------

    def _run_bot_thread(self) -> None:
        """Entry point for the bot daemon thread."""
        asyncio.set_event_loop(self._bot_loop)
        self._bot_loop.run_until_complete(self._start_bot())
        self._bot_loop.run_forever()

    async def _start_bot(self) -> None:
        """Initialise the Application and start Telegram update polling."""
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(
            drop_pending_updates=True,  # Ignore queued updates from before startup
            allowed_updates=["callback_query"],
        )
        LOG.info("Telegram bot polling started")

    async def _stop_bot(self) -> None:
        """Graceful shutdown (called from the bot loop)."""
        await self._app.updater.stop()
        await self._app.stop()
        await self._app.shutdown()

    # ------------------------------------------------------------------
    # Callback query handler (runs in bot event loop)
    # ------------------------------------------------------------------

    async def _on_callback_query(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle Approve / Reject button presses from the Telegram user."""
        query = update.callback_query
        if query is None:
            return

        data = query.data or ""
        parts = data.split(":", 1)
        if len(parts) != 2:
            LOG.warning("Unexpected callback_data format: %r", data)
            return

        action, challenge_id = parts
        approver = query.from_user.full_name if query.from_user else "unknown"

        if action == _ACTION_APPROVE:
            new_status = ChallengeStatus.APPROVED
            status_emoji = "✅"
            status_text = "Approved"
        elif action == _ACTION_REJECT:
            new_status = ChallengeStatus.REJECTED
            status_emoji = "❌"
            status_text = "Rejected"
        else:
            LOG.warning("Unknown callback action: %r", action)
            return

        # Update results BEFORE any network call — PTB's HTTP client may hang
        with self._results_lock:
            self._results[challenge_id] = new_status

        LOG.info(
            "2FA challenge %s %s by %s",
            challenge_id[:8], status_text.lower(), approver,
        )

        # Best-effort UI updates — failures here don't affect the decision
        try:
            await query.answer()
        except Exception as exc:
            LOG.debug("Could not answer callback query: %s", exc)

        try:
            original_text = query.message.text if query.message else ""
            await query.edit_message_text(
                text=f"{original_text}\n\n{status_emoji} *{status_text}* by {approver}",
                parse_mode="Markdown",
                reply_markup=None,
            )
        except Exception as exc:
            LOG.debug("Could not edit Telegram message: %s", exc)

    # ------------------------------------------------------------------
    # BaseAuthProvider interface
    # ------------------------------------------------------------------

    async def issue_challenge(self, context: ChallengeContext) -> ChallengeResponse:
        """
        Send an approval request to the Telegram approver.

        Uses a direct httpx call to the Telegram Bot API — independent of the
        PTB Application's internal HTTP client and event loop — to avoid
        connection-pool contention with the polling loop.

        Returns immediately with status=PENDING once the message is sent.
        """
        import httpx

        challenge_id = str(uuid.uuid4())

        # Pre-register the challenge as PENDING
        with self._results_lock:
            self._results[challenge_id] = ChallengeStatus.PENDING

        args_display = " ".join(context.args) if context.args else "(none)"
        text = (
            "🔐 *MCP-Sentinel — Execution Approval Required*\n\n"
            f"*Principal:* `{context.initiator_id}`\n"
            f"*Target Agent:* `{context.target_agent_id}`\n"
            f"*Command:* `{context.command}`\n"
            f"*Args:* `{args_display}`\n"
            f"*Request ID:* `{context.request_id[:8]}…`\n\n"
            "_Please approve or reject this execution request._"
        )
        payload = {
            "chat_id": self._approver_chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "reply_markup": {
                "inline_keyboard": [[
                    {"text": "✅ Approve", "callback_data": f"{_ACTION_APPROVE}:{challenge_id}"},
                    {"text": "❌ Reject",  "callback_data": f"{_ACTION_REJECT}:{challenge_id}"},
                ]]
            },
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{self._bot_token}/sendMessage",
                    json=payload,
                )
            resp.raise_for_status()
            telegram_message_id = resp.json()["result"]["message_id"]
        except Exception as exc:
            LOG.error("Failed to send Telegram challenge message: %s", exc)
            with self._results_lock:
                self._results.pop(challenge_id, None)
            raise RuntimeError(f"Telegram notification failed: {exc}") from exc

        LOG.info(
            "Challenge issued: challenge_id=%s telegram_msg_id=%s",
            challenge_id[:8], telegram_message_id,
        )
        return ChallengeResponse(
            challenge_id=challenge_id,
            status=ChallengeStatus.PENDING,
            external_ref=str(telegram_message_id),
        )

    async def verify_challenge(
        self, challenge_id: str, external_ref: str | None
    ) -> ChallengeResponse:
        """
        Return the current status of a challenge by reading the results dict.

        This is a simple dict lookup — the real update happens in
        ``_on_callback_query`` when the user presses a button.
        """
        with self._results_lock:
            status = self._results.get(challenge_id, ChallengeStatus.EXPIRED)

        return ChallengeResponse(
            challenge_id=challenge_id,
            status=status,
            external_ref=external_ref,
        )

