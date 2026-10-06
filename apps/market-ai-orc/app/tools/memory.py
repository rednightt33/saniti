"""read_conversation_memory (EXEC-C, AI_ENABLE_RUN_MEMORY): what an earlier run of this conversation kept, read from
"AI_conversation_run_memory" (app/run_memory.py). READS, no model call; on every desk (EXEC-T, H)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..run_memory import DESCRIPTION, MemoryStore, ReadMemoryArgs, read_memory
from .artifacts import current_results
from .registry import ToolSpec
from .request_data import current_conversation_id

NAME = "read_conversation_memory"


def memory_spec(store: MemoryStore, *, max_result_bytes: int = 60_000) -> ToolSpec:
    def handler(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, ReadMemoryArgs)
        results = current_results.get()
        conversation_id = current_conversation_id.get()
        result_store = results.store if results is not None else None

        def code(execution_id: str) -> dict[str, Any] | None:
            if result_store is None or not conversation_id:
                return None
            try:
                return result_store.execution(conversation_id, execution_id)
            except Exception:  # noqa: BLE001 - the memory's own copy is read instead
                return None

        return read_memory(store, conversation_id, arguments, record=results.record if results is not None else None,
                           code_reader=code)

    return ToolSpec(name=NAME, effect="READS", description=DESCRIPTION, arguments_model=ReadMemoryArgs,
                    handler=handler, timeout_seconds=15.0, max_result_bytes=max_result_bytes)
