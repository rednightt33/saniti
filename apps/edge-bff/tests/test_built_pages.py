"""ERRORS M546 (its test-out wf_c72ae04c-a73, admin-support page-tests-records-2): the browser tests point every page's
frame folder at the build the image would copy there (conftest.built_pages, derived from the Dockerfile's COPY lines).
This locks the derivation: every folder app/main.py serves a page from has its COPY line, so a new page is in the image
and in the browser tests alike, and the fixture applies to every test that opens a browser."""
from pathlib import Path

from app import main
from conftest import image_builds, opens_browser


def test_every_page_folder_main_serves_is_copied_into_the_image_from_a_build():
    folders = {name: value for name, value in vars(main).items()
               if name.endswith('_APP') and isinstance(value, Path) and value.parent == main.STATIC}
    builds = image_builds()
    assert len(folders) >= 9, folders                             # the Terminal, the Backtest (both lab builds too), ...
    missing = sorted(f'{name} (static/{value.name})' for name, value in folders.items() if value.name not in builds)
    assert not missing, f'a page folder without its COPY line in apps/edge-bff/Dockerfile: {missing}'
    assert builds['admin-app'].parts[-2:] == ('admin', 'dist') and builds['backtest-app-lab'].parts[-2:] == ('backtest', 'dist-lab')


def test_the_fixture_applies_to_a_test_that_opens_a_browser():
    import test_admin_page

    class Item:
        def __init__(self, function):
            self.function, self.fixturenames, self._fixtureinfo = function, [], None
    assert opens_browser(Item(test_admin_page.test_a_sign_in_through_the_authenticator_code_keeps_the_page_it_was_shown_at))
    assert not opens_browser(Item(test_every_page_folder_main_serves_is_copied_into_the_image_from_a_build))
