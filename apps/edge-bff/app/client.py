import re
from urllib.parse import urlsplit
import httpx


class OrcError(Exception):
    def __init__(self, code='ORC_UNAVAILABLE', status=503, ambiguous=False):
        self.code, self.status, self.ambiguous = code, status, ambiguous
        super().__init__(code)


PRIVATE_KEYS = {'reasoning', 'reasoning_content', 'reasoning_details', 'thinking', 'chain_of_thought',
                'encrypted_content', 'tool_trace', 'audit_trace', 'raw_provider_response', 'system_prompt', 'memo_note',
                'api_key', 'authorization', 'password', 'session_secret', 'token', 'reasoning_summary', 'summarized_reasoning'}


def public_data(value):
    if isinstance(value, dict):
        return {k: public_data(v) for k, v in value.items() if k.lower() not in PRIVATE_KEYS}
    if isinstance(value, list):
        return [public_data(v) for v in value]
    if isinstance(value, str):
        # Redact service addresses even when embedded in a provider/error/answer string.
        return re.sub(r'(?:https?://)?[A-Za-z0-9_.-]+\.railway\.internal(?::\d+)?[^\s<>"\[\]()]*', '[internal address]', value)
    return value


class OrcClient:
    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client or httpx.Client(base_url=settings.orc_url, timeout=settings.orc_timeout_seconds,
                                             follow_redirects=False, trust_env=False)

    def _call(self, method, path, owner, body=None):
        try:
            response = self.client.request(method, path,
                headers={'Authorization': f'Bearer {self.settings.orc_key}', 'X-Saniti-Owner': owner}, json=body)
        except httpx.HTTPError as e:
            raise OrcError(ambiguous=method == 'POST') from e
        if response.status_code == 404:
            if path.startswith('/v1/agent/requests/'):
                try:
                    code = response.json().get('detail', {}).get('code')
                except (ValueError, AttributeError):
                    code = None
                # A missing route or disabled store is not evidence that a request never ran.
                if code != 'REQUEST_NOT_FOUND':
                    raise OrcError('ORC_REQUEST_READ_UNAVAILABLE')
            return None
        if response.status_code != 200:
            # Never forward upstream error text, addresses or credentials.
            code = 'ORC_REQUEST_REJECTED' if response.status_code in (400, 409, 422) else 'ORC_UNAVAILABLE'
            raise OrcError(code, response.status_code if response.status_code in (400, 409, 422) else 503,
                           ambiguous=method == 'POST' and response.status_code >= 500)
        try:
            return public_data(response.json())
        except ValueError as e:
            raise OrcError('ORC_INVALID_RESPONSE', ambiguous=method == 'POST') from e

    def run(self, owner, request_id, payload):
        # Strict whitelist; no browser provider/path/history overrides. EXEC-MODELS: the model and reasoning level
        # are forwarded and checked by Orc against its offered models (an unknown one is refused there).
        body = {k: payload[k] for k in ('message', 'conversation_id', 'chosen_option', 'plan_reply', 'model',
                                        'reasoning_level', 'lane', 'attached_selection', 'attachments')
                if k in payload and payload[k] not in (None, [])}
        body.update(request_id=request_id, history_mode='SERVER')
        return self._call('POST', '/v1/agent/run', owner, body)

    def request(self, owner, request_id):
        return self._call('GET', f'/v1/agent/requests/{request_id}', owner)

    def execution_ready(self, owner):
        state = self._call('GET', '/v1/agent/readiness', owner)
        # Rolling deploy compatibility with the older Orc, which has no route.
        return state is None or state.get('status') == 'ready'

    def stop(self, owner, request_id):
        """The stop button: STOPPING when Orc flagged the running request, NOT_RUNNING when it is not running there
        (not dispatched yet, finished, or another owner's). Orc answers 202 or 404; never a POST replay."""
        try:
            response = self.client.post(f'/v1/agent/run/{request_id}/stop',
                headers={'Authorization': f'Bearer {self.settings.orc_key}', 'X-Saniti-Owner': owner})
        except httpx.HTTPError as e:
            raise OrcError() from e
        if response.status_code == 202:
            return 'STOPPING'
        if response.status_code == 404:
            return 'NOT_RUNNING'
        raise OrcError()

    def progress(self, owner, request_id):
        """EXEC-IMPL-1016 Fase 4.3 (UI-1015B): the steps of a running request in plain words; None when Orc does not
        run it (not dispatched yet, finished long ago, or another owner's). Labels and times only."""
        try:
            response = self.client.get(f'/v1/agent/requests/{request_id}/progress',
                headers={'Authorization': f'Bearer {self.settings.orc_key}', 'X-Saniti-Owner': owner})
        except httpx.HTTPError as e:
            raise OrcError() from e
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise OrcError()
        try:
            data = response.json()
        except ValueError as e:
            raise OrcError() from e
        steps = [{'label': str(s.get('label') or '')[:80], 'state': str(s.get('state') or '')[:12],
                  'started_ms': int(s.get('started_ms') or 0), 'duration_ms': int(s.get('duration_ms') or 0)}
                 for s in (data.get('steps') or [])[:60] if isinstance(s, dict)]
        return {'status': 'FINISHED' if data.get('status') == 'FINISHED' else 'RUNNING',
                'elapsed_ms': int(data.get('elapsed_ms') or 0), 'steps': steps,
                'earlier_steps': int(data.get('earlier_steps') or 0)}

    def export_table(self, owner, conversation_id, output_id, columns, titles):
        """The table download of an answer (user 2026-10-20): Orc writes every row of a kept table as XLSX with the
        columns and titles the answer shows and keeps it for the export download route. Returns the export's id, file
        name and size; Orc's own refusal code is kept (EXPORT_IN_PROGRESS, OUTPUT_NOT_FOUND, ...), never its text."""
        try:
            response = self.client.post(f'/v1/conversations/{conversation_id}/outputs/{output_id}/export',
                json={'columns': columns, 'titles': titles},
                headers={'Authorization': f'Bearer {self.settings.orc_key}', 'X-Saniti-Owner': owner})
        except httpx.HTTPError as e:
            raise OrcError('EXPORT_FAILED') from e
        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.status_code != 200:
            detail = data.get('detail') if isinstance(data, dict) else None
            code = detail.get('code') if isinstance(detail, dict) else None
            code = code if isinstance(code, str) and re.fullmatch(r'[A-Z_]{3,60}', code) else 'EXPORT_FAILED'
            raise OrcError(code, response.status_code if response.status_code in (404, 409, 410, 422) else 503)
        return {k: public_data(data.get(k)) for k in ('export_id', 'file_name', 'size_bytes', 'format')
                if isinstance(data, dict) and data.get(k) is not None}

    def models(self, owner):
        """EXEC-MODELS: Orc's offered models, their reasoning levels and their prices per one million tokens."""
        return self._call('GET', '/v1/models', owner)

    def manual(self, owner, method, path, body=None):
        """EXEC-MANUAL (troubleshooting): the model calls waiting for Claude, and Claude's reply to one; Orc answers
        404 while its switch is off. Returns (status code, body)."""
        try:
            response = self.client.request(method, '/v1/dev/manual/steps' + path, json=body,
                headers={'Authorization': f'Bearer {self.settings.orc_key}', 'X-Saniti-Owner': owner})
            data = response.json()
        except (httpx.HTTPError, ValueError) as e:
            raise OrcError() from e
        return response.status_code, public_data(data)

    def messages(self, owner, conversation_id, after=-1, limit=20):
        return self._call('GET', f'/v1/conversations/{conversation_id}/messages?after={after}&limit={limit}', owner)

    def close(self):
        self.client.close()
