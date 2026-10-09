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
        # Strict whitelist; no browser model/provider/path/history overrides.
        body = {k: payload[k] for k in ('message', 'conversation_id', 'chosen_option', 'plan_reply') if k in payload}
        body.update(request_id=request_id, history_mode='SERVER')
        return self._call('POST', '/v1/agent/run', owner, body)

    def request(self, owner, request_id):
        return self._call('GET', f'/v1/agent/requests/{request_id}', owner)

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

    def messages(self, owner, conversation_id, after=-1, limit=20):
        return self._call('GET', f'/v1/conversations/{conversation_id}/messages?after={after}&limit={limit}', owner)

    def close(self):
        self.client.close()
