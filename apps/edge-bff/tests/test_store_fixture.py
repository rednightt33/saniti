"""ERRORS M539: the `store` fixture closes its connection pool when its test ends. Left open, the idle connections of
every test piled up until a later test's setup failed with 'too many clients already' (CI 45043526824, 5 errors in
test_terminal_fix_round). The first test opens the pool; the second, which pytest runs after it in this file, finds it
closed."""

SEEN = []


def test_a_test_opens_the_stores_pool(store):
    with store.connect() as c:
        c.execute('SELECT 1')
    assert store._pool is not None
    SEEN.append(store)


def test_the_store_of_the_test_before_was_closed_at_its_end():
    assert SEEN, 'run with the test above (pytest keeps the order of a file)'
    assert SEEN[-1]._pool is None, 'the store fixture left its pool open (tests/conftest.py, ERRORS M539)'
