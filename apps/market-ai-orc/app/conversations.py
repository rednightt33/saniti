"""Server-side conversation history (AI_ENABLE_CONVERSATION_STORE; implementation plan 2026-09-27, phase H1).

With history_mode SERVER a caller sends one message per request and the orchestrator reads the earlier turns from
PostgreSQL ("AI_conversation", "AI_conversation_turn"; migration 20260927_002) instead of receiving a history.

Ownership: the owner is the X-Saniti-Owner header of the trusted server-side caller that holds the internal bearer
(DEFAULT_OWNER without the header). Every lookup checks it; a conversation of another owner reads as not found. The
model never supplies or sees the owner.

One turn at a time per conversation: a short transaction claims the conversation's lease (active request id, lease
generation, expiry) and allocates the turn index; the model runs outside any transaction; the response is stored
only with the generation it started with (compare-and-set), so a runner whose lease lapsed and was taken over cannot
overwrite the newer state. A retry of the same request_id with the same content returns the stored response without
a new run; different content under the same request_id is refused.

Research Plans (phase H2, app/conversation_plans.py): the conversation state keeps the latest plan the backend
issued, so the caller sends only the reply (free text, or plan_reply with an explicit action); the plan_reply is
checked against that state before the turn is allocated, and the state moves with the stored response.

Retention: a conversation expires AI_CONVERSATION_RETENTION_DAYS after its last activity; cleanup deletes it with
its turns in bounded batches. Only completed turns with an assistant text become history; tool traces, datasets and
hidden reasoning are never stored here.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
import threading
from dataclasses import dataclass, field
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from . import conversation_plans as plans
from .research_plan import ContinuationIn
from .schemas import MAX_HISTORY_ITEMS, MAX_MESSAGE_CHARACTERS, AgentRunRequest, AgentRunResponse, HistoryMessage

logger = logging.getLogger("market_ai_orc")

OWNER_HEADER = "X-Saniti-Owner"
DEFAULT_OWNER = "default"
OWNER_RE = re.compile(r"^[A-Za-z0-9._:@-]{1,128}$")
CONVERSATION_ID_RE = re.compile(r"^conv_[0-9a-f]{32}$")
MAX_ASSISTANT_TEXT = 40000
MESSAGES_PAGE_DEFAULT = 20
MESSAGES_PAGE_MAX = 50


class ConversationError(Exception):
    """A refused conversation request: code and message for the caller, and the HTTP status."""

    def __init__(self, code: str, message: str, http_status: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def owner_from_header(value: str | None) -> str:
    if value is None or not value.strip():
        return DEFAULT_OWNER
    value = value.strip()
    if not OWNER_RE.fullmatch(value):
        raise ConversationError("INVALID_OWNER", f"{OWNER_HEADER} must match {OWNER_RE.pattern}.", 400)
    return value


def reuse_key(owner: str, conversation_id: str) -> str:
    """The key the sandbox scopes conversation reuse by (S1/S2): derived from the owner and the conversation, so it
    is not the conversation id and another owner's key never matches. Set by the application, never by the model."""
    return "ck_" + hashlib.sha256(f"{owner}\n{conversation_id}".encode()).hexdigest()[:32]


def fingerprint(request: AgentRunRequest) -> str:
    """The content a retry of the same request_id must repeat: conversation, message, metadata, continuation and
    plan_reply."""
    body = {"conversation_id": request.conversation_id, "message": request.message, "metadata": request.metadata,
            "continuation": request.continuation.model_dump(mode="json") if request.continuation else None}
    if request.plan_reply is not None:  # absent from the fingerprints stored before phase H2
        body["plan_reply"] = request.plan_reply.model_dump(mode="json")
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def assistant_text(result: AgentRunResponse) -> str | None:
    """What later turns see as the assistant message: the clarification question for a CLARIFICATION, else the
    answer. None without a response (a failed run), so it never becomes history."""
    response = result.response
    if response is None:
        return None
    text = response.clarification_question if response.response_type == "CLARIFICATION" \
        and response.clarification_question else response.answer
    return (text or "")[:MAX_ASSISTANT_TEXT] or None


@dataclass
class TurnStart:
    conversation_id: str
    turn_index: int
    generation: int
    created: bool
    history: list[HistoryMessage] = field(default_factory=list)
    replay: dict[str, Any] | None = None          # the stored response of an identical earlier request
    state: dict[str, Any] = field(default_factory=dict)   # the conversation state when the turn started
    continuation: ContinuationIn | None = None    # the latest pending Research Plan, built by the server (H2)


class ConversationStore:
    """PostgreSQL access through the market_ai_conversation login (CONVERSATION_DATABASE_URL)."""

    def __init__(self, url: str, *, retention_days: int, lease_seconds: int, connect_timeout_seconds: int = 5,
                 max_history_turns: int = MAX_HISTORY_ITEMS // 2) -> None:
        self.url = url
        self.retention_days = retention_days
        self.lease_seconds = lease_seconds
        self.connect_timeout_seconds = connect_timeout_seconds
        self.max_history_turns = max_history_turns

    def _connect(self) -> psycopg.Connection:
        try:
            return psycopg.connect(self.url, row_factory=dict_row, connect_timeout=self.connect_timeout_seconds)
        except psycopg.Error as exc:
            raise ConversationError("CONVERSATION_STORE_UNAVAILABLE", "The conversation store is unavailable; "
                                    "retry later or use history_mode CLIENT.", 503) from exc

    # ------------------------------------------------------------------------------------------------ turns

    def begin(self, owner: str, request: AgentRunRequest, request_fingerprint: str) -> TurnStart:
        try:
            with self._connect() as connection:
                return self._begin(connection, owner, request, request_fingerprint)
        except psycopg.errors.UniqueViolation:
            # the same request_id started concurrently: answer like a retry of a running turn
            with self._connect() as connection:
                return self._begin(connection, owner, request, request_fingerprint)
        except ConversationError:
            raise
        except psycopg.Error as exc:
            raise ConversationError("CONVERSATION_STORE_UNAVAILABLE", "The conversation store failed; retry later "
                                    "or use history_mode CLIENT.", 503) from exc

    def _begin(self, connection: psycopg.Connection, owner: str, request: AgentRunRequest,
               request_fingerprint: str) -> TurnStart:
        existing = connection.execute(
            '''SELECT t.conversation_id, t.turn_index, t.status, t.request_fingerprint, t.response,
                      t.lease_generation, c.owner_key, c.state,
                      c.active_request_id = t.request_id AND c.lease_generation = t.lease_generation
                          AND c.lease_expires_at > CURRENT_TIMESTAMP AS lease_held
               FROM public."AI_conversation_turn" t JOIN public."AI_conversation" c USING (conversation_id)
               WHERE t.request_id = %s FOR UPDATE OF c''', (request.request_id,)).fetchone()
        if existing is not None:
            same = (existing["owner_key"] == owner and existing["request_fingerprint"] == request_fingerprint
                    and request.conversation_id in (None, existing["conversation_id"]))
            if not same:
                raise ConversationError("REQUEST_ID_CONFLICT", "This request_id was already used for a different "
                                        "request; send a new request_id for a new message.", 409)
            if existing["status"] == "COMPLETED":
                return TurnStart(existing["conversation_id"], existing["turn_index"], existing["lease_generation"],
                                 False, replay=existing["response"],
                                 state=existing["state"] if isinstance(existing["state"], dict) else {})
            if existing["status"] == "RUNNING" and existing["lease_held"]:
                raise ConversationError("TURN_IN_PROGRESS", "This request is still running; retry the same "
                                        "request_id later to receive its response.", 409)
            if existing["status"] == "RUNNING":
                # its runner died or was taken over: the turn ends INTERRUPTED and the lease is released
                self._interrupt(connection, existing["conversation_id"], request.request_id,
                                existing["lease_generation"])
                existing["status"] = "INTERRUPTED"
            raise ConversationError("TURN_NOT_COMPLETED", f"This request ended {existing['status']} without a "
                                    "stored response; send the message again with a new request_id.", 409)

        created = request.conversation_id is None
        if created:
            conversation_id = f"conv_{secrets.token_hex(16)}"
            connection.execute(
                '''INSERT INTO public."AI_conversation" (conversation_id, owner_key, expires_at)
                   VALUES (%s, %s, CURRENT_TIMESTAMP + make_interval(days => %s))''',
                (conversation_id, owner, self.retention_days))
        else:
            conversation_id = request.conversation_id
            if not CONVERSATION_ID_RE.fullmatch(conversation_id or ""):
                raise ConversationError("CONVERSATION_NOT_FOUND", "No such conversation for this owner.", 404)
        row = connection.execute(
            '''SELECT next_turn_index, active_request_id, lease_generation, state,
                      lease_expires_at IS NOT NULL AND lease_expires_at > CURRENT_TIMESTAMP AS leased
               FROM public."AI_conversation" WHERE conversation_id = %s AND owner_key = %s FOR UPDATE''',
            (conversation_id, owner)).fetchone()
        if row is None:
            raise ConversationError("CONVERSATION_NOT_FOUND", "No such conversation for this owner.", 404)
        state = row["state"] if isinstance(row["state"], dict) else {}
        try:
            # before the turn is allocated, so a refused plan_reply leaves no turn behind
            continuation = plans.continuation_for(state, request)
        except plans.PlanReplyError as error:
            raise ConversationError(error.code, error.message, error.http_status) from None
        if row["active_request_id"] is not None:
            if row["leased"]:
                raise ConversationError("CONVERSATION_BUSY", "Another message of this conversation is still "
                                        "running; wait for its response, then send the next message.", 409)
            # the lease lapsed: the earlier runner may not store its response any more (fenced by generation)
            connection.execute(
                '''UPDATE public."AI_conversation_turn"
                   SET status = 'INTERRUPTED', error_code = 'LEASE_EXPIRED', completed_at = CURRENT_TIMESTAMP
                   WHERE request_id = %s AND status = 'RUNNING' ''', (row["active_request_id"],))
            logger.warning(json.dumps({"event": "conversation_lease_taken_over", "conversation_id": conversation_id,
                                       "interrupted_request_id": row["active_request_id"]}))
        generation = int(row["lease_generation"]) + 1
        turn_index = int(row["next_turn_index"])
        connection.execute(
            '''UPDATE public."AI_conversation"
               SET next_turn_index = next_turn_index + 1, active_request_id = %s, lease_generation = %s,
                   lease_expires_at = CURRENT_TIMESTAMP + make_interval(secs => %s),
                   updated_at = CURRENT_TIMESTAMP,
                   expires_at = CURRENT_TIMESTAMP + make_interval(days => %s)
               WHERE conversation_id = %s''',
            (request.request_id, generation, self.lease_seconds, self.retention_days, conversation_id))
        connection.execute(
            '''INSERT INTO public."AI_conversation_turn" (request_id, conversation_id, turn_index,
                   request_fingerprint, user_message, status, lease_generation)
               VALUES (%s, %s, %s, %s, %s, 'RUNNING', %s)''',
            (request.request_id, conversation_id, turn_index, request_fingerprint, request.message, generation))
        rows = connection.execute(
            '''SELECT user_message, assistant_text FROM public."AI_conversation_turn"
               WHERE conversation_id = %s AND status = 'COMPLETED' AND assistant_text IS NOT NULL
               ORDER BY turn_index DESC LIMIT %s''', (conversation_id, self.max_history_turns)).fetchall()
        history: list[HistoryMessage] = []
        for item in reversed(rows):
            history.append(HistoryMessage(role="user", content=item["user_message"][:MAX_MESSAGE_CHARACTERS]))
            history.append(HistoryMessage(role="assistant",
                                          content=item["assistant_text"][:MAX_MESSAGE_CHARACTERS]))
        return TurnStart(conversation_id, turn_index, generation, created, history=history, state=state,
                         continuation=continuation)

    @staticmethod
    def _interrupt(connection: psycopg.Connection, conversation_id: str, request_id: str, generation: int) -> None:
        connection.execute(
            '''UPDATE public."AI_conversation_turn"
               SET status = 'INTERRUPTED', error_code = 'LEASE_EXPIRED', completed_at = CURRENT_TIMESTAMP
               WHERE request_id = %s AND status = 'RUNNING' ''', (request_id,))
        connection.execute(
            '''UPDATE public."AI_conversation" SET active_request_id = NULL, lease_expires_at = NULL
               WHERE conversation_id = %s AND active_request_id = %s AND lease_generation = %s''',
            (conversation_id, request_id, generation))

    def finish(self, start: TurnStart, request_id: str, result: AgentRunResponse) -> bool:
        """Store the response, the conversation state (the latest Research Plan, H2) and release the lease, only with
        the generation the turn started with. False when the turn was taken over (its lease lapsed) or the store
        failed: the caller is told it was not saved."""
        body = result.model_dump(mode="json")
        response = result.response
        state = plans.advance(start.state, result, request_id, start.turn_index)
        try:
            with self._connect() as connection:
                stored = connection.execute(
                    '''UPDATE public."AI_conversation_turn" t
                       SET status = 'COMPLETED', run_status = %s, response_type = %s, assistant_text = %s,
                           response = %s, error_code = %s, completed_at = CURRENT_TIMESTAMP
                       FROM public."AI_conversation" c
                       WHERE t.request_id = %s AND t.status = 'RUNNING' AND t.lease_generation = %s
                         AND c.conversation_id = t.conversation_id AND c.conversation_id = %s
                         AND c.active_request_id = %s AND c.lease_generation = %s''',
                    (result.status, response.response_type if response else None, assistant_text(result),
                     Jsonb(body), result.error.code if result.error else None, request_id, start.generation,
                     start.conversation_id, request_id, start.generation)).rowcount
                if stored != 1:
                    connection.rollback()
                    return False
                connection.execute(
                    '''UPDATE public."AI_conversation"
                       SET active_request_id = NULL, lease_expires_at = NULL, updated_at = CURRENT_TIMESTAMP,
                           expires_at = CURRENT_TIMESTAMP + make_interval(days => %s), state = %s
                       WHERE conversation_id = %s AND active_request_id = %s AND lease_generation = %s''',
                    (self.retention_days, Jsonb(state), start.conversation_id, request_id, start.generation))
            start.state = state
            return True
        except (psycopg.Error, ConversationError):
            logger.exception(json.dumps({"event": "conversation_store_failed", "request_id": request_id,
                                         "conversation_id": start.conversation_id}))
            return False

    def abandon(self, start: TurnStart, request_id: str, code: str) -> None:
        """Mark a turn FAILED and release the lease when the run raised instead of returning a response."""
        try:
            with self._connect() as connection:
                released = connection.execute(
                    '''UPDATE public."AI_conversation"
                       SET active_request_id = NULL, lease_expires_at = NULL, updated_at = CURRENT_TIMESTAMP
                       WHERE conversation_id = %s AND active_request_id = %s AND lease_generation = %s''',
                    (start.conversation_id, request_id, start.generation)).rowcount
                if released == 1:
                    connection.execute(
                        '''UPDATE public."AI_conversation_turn"
                           SET status = 'FAILED', error_code = %s, completed_at = CURRENT_TIMESTAMP
                           WHERE request_id = %s AND status = 'RUNNING' ''', (code, request_id))
        except (psycopg.Error, ConversationError):
            logger.exception(json.dumps({"event": "conversation_store_failed", "request_id": request_id}))

    # ------------------------------------------------------------------------------------------------ reading

    def messages(self, owner: str, conversation_id: str, after: int | None, limit: int | None) -> dict[str, Any]:
        limit = min(max(limit or MESSAGES_PAGE_DEFAULT, 1), MESSAGES_PAGE_MAX)
        if not CONVERSATION_ID_RE.fullmatch(conversation_id):
            raise ConversationError("CONVERSATION_NOT_FOUND", "No such conversation for this owner.", 404)
        try:
            with self._connect() as connection:
                conversation = connection.execute(
                    '''SELECT conversation_id, created_at, updated_at, expires_at, next_turn_index, state,
                              active_request_id IS NOT NULL AS running
                       FROM public."AI_conversation" WHERE conversation_id = %s AND owner_key = %s''',
                    (conversation_id, owner)).fetchone()
                if conversation is None:
                    raise ConversationError("CONVERSATION_NOT_FOUND", "No such conversation for this owner.", 404)
                rows = connection.execute(
                    '''SELECT turn_index, request_id, status, run_status, response_type, user_message, response,
                              error_code, created_at, completed_at
                       FROM public."AI_conversation_turn"
                       WHERE conversation_id = %s AND turn_index > %s ORDER BY turn_index LIMIT %s''',
                    (conversation_id, -1 if after is None else after, limit + 1)).fetchall()
        except ConversationError:
            raise
        except psycopg.Error as exc:
            raise ConversationError("CONVERSATION_STORE_UNAVAILABLE", "The conversation store failed.", 503) from exc
        items = [{key: (value.isoformat() if hasattr(value, "isoformat") else value) for key, value in row.items()}
                 for row in rows[:limit]]
        has_more = len(rows) > limit
        return {
            "conversation_id": conversation_id,
            "created_at": conversation["created_at"].isoformat(),
            "updated_at": conversation["updated_at"].isoformat(),
            "expires_at": conversation["expires_at"].isoformat(),
            "turn_count": int(conversation["next_turn_index"]),
            "running": bool(conversation["running"]),
            "research_plan": plans.summary(conversation["state"]),
            "messages": items,
            "has_more": has_more,
            "next_after": items[-1]["turn_index"] if has_more and items else None,
        }

    # ------------------------------------------------------------------------------------------------ upkeep

    def recover(self) -> int:
        """Release lapsed leases and mark their running turns INTERRUPTED (a process that died mid-run)."""
        with self._connect() as connection:
            rows = connection.execute(
                '''WITH lapsed AS (
                       SELECT conversation_id, active_request_id FROM public."AI_conversation"
                       WHERE active_request_id IS NOT NULL AND lease_expires_at <= CURRENT_TIMESTAMP
                       FOR UPDATE SKIP LOCKED),
                   released AS (
                       UPDATE public."AI_conversation" c SET active_request_id = NULL, lease_expires_at = NULL
                       FROM lapsed WHERE c.conversation_id = lapsed.conversation_id
                       RETURNING lapsed.active_request_id)
                   UPDATE public."AI_conversation_turn" t
                   SET status = 'INTERRUPTED', error_code = 'LEASE_EXPIRED', completed_at = CURRENT_TIMESTAMP
                   FROM released WHERE t.request_id = released.active_request_id AND t.status = 'RUNNING'
                   RETURNING t.request_id''').fetchall()
        return len(rows)

    def cleanup(self, batch: int = 500) -> int:
        """Delete up to batch expired conversations (their turns cascade); a running one is left for later."""
        with self._connect() as connection:
            return connection.execute(
                '''DELETE FROM public."AI_conversation" WHERE conversation_id IN (
                       SELECT conversation_id FROM public."AI_conversation"
                       WHERE expires_at <= CURRENT_TIMESTAMP
                         AND (active_request_id IS NULL OR lease_expires_at <= CURRENT_TIMESTAMP)
                       ORDER BY expires_at LIMIT %s FOR UPDATE SKIP LOCKED)''', (batch,)).rowcount

    def upkeep(self) -> None:
        try:
            interrupted = self.recover()
            deleted = self.cleanup()
            if interrupted or deleted:
                logger.info(json.dumps({"event": "conversation_upkeep", "interrupted": interrupted,
                                        "deleted": deleted}))
        except (psycopg.Error, ConversationError):
            logger.exception(json.dumps({"event": "conversation_upkeep_failed"}))


class UpkeepThread:
    """Runs ConversationStore.upkeep at start and then every interval_seconds, in a daemon thread."""

    def __init__(self, store: ConversationStore, interval_seconds: int) -> None:
        self.store = store
        self.interval_seconds = interval_seconds
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="conversation-upkeep", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()

    def _run(self) -> None:
        while not self.stop_event.is_set():
            self.store.upkeep()
            self.stop_event.wait(self.interval_seconds)
