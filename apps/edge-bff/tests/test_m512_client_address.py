"""ERRORS M512 (the probe of CONTRACT.md section 4, the user's "1a", 2026-11-20): Railway's edge drops every
X-Forwarded-For and X-Real-IP line a client writes and sends "<client>, <edge node>"; on app.edgefinance.id the right-most
entry was the edge node (152.233.40.1 or .2) on every request, whatever the client sent. The client's key is therefore
the entry left of the edge node's: the visitor key and the sign-in, reset and mail counters read it (throttle.
forwarded_hop), so two visitors behind the same edge node are two clients, and a line a client writes never decides."""
from types import SimpleNamespace

from app import principal, throttle


def request(*lines):
    class Headers:
        def getlist(self, name):
            return list(lines) if name == 'x-forwarded-for' else []
    return SimpleNamespace(headers=Headers(), client=None)


def test_the_client_is_the_entry_left_of_the_edge_node():
    # what the probe saw: the client's public address, then the edge node's
    assert throttle.forwarded_hop(request('160.79.106.149, 152.233.40.1')) == '160.79.106.149'
    # two visitors behind one edge node are two clients (the right-most would have made them one)
    a = principal.client_of(request('203.0.113.7, 152.233.40.1'))
    b = principal.client_of(request('198.51.100.9, 152.233.40.1'))
    assert a == '203.0.113.7' and b == '198.51.100.9' and a != b


def test_a_line_the_client_writes_never_decides():
    # if an edge ever kept a client's own lines, they would stand left of the client's hop
    for forged in ('10.0.0.1', '1.1.1.1, 2.2.2.2'):
        assert throttle.forwarded_hop(request(forged, '203.0.113.7, 152.233.40.1')) == '203.0.113.7'
        assert throttle.forwarded_hop(request(f'{forged}, 203.0.113.7, 152.233.40.1')) == '203.0.113.7'


def test_a_header_without_the_edge_hop_gives_its_only_entry_and_no_header_gives_none():
    assert throttle.forwarded_hop(request('203.0.113.7')) == '203.0.113.7'       # a private caller or a local test
    assert throttle.forwarded_hop(request()) is None
    assert principal.client_of(request('not-an-address, 152.233.40.1')) is None  # fail closed
