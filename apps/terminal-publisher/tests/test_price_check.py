"""EXEC-PRICE-DISTORTION (ERRORS M560): the publisher's close side (`price` of the basis block, the Telegram report, the
Backtest's settled actions) follows the Screener's pricecheck.ts on the same cases as
apps/edge-bff/screener/tests/core/pricecheck.test.ts: the five actions of 2026-09-22..10-14 as stored now (pulled again:
adjusted) and before the pull (raw), a split either way, an action under 10 % (no side), a missing close."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from publisher import price_check_factor, price_check_side  # noqa: E402

# ticker, old, new, exercise, close before the ex date now, close on the ex date, close before the pull (raw)
RIGHTS = [('VKTR', 35, 12, 200, 626.91466, 670, 835), ('AHAP', 7, 5, 50, 72.1666, 78, 88),
          ('BUVA', 4, 1, 250, 521.99955, 520, 590), ('FORU', 100, 46235, 126, 131.25376, 176, 2560)]


def test_rights_issues_pulled_again_read_adjusted_and_raw_before_the_pull():
    for t, old, new, x, now, on_ex, raw in RIGHTS:
        assert price_check_factor('RIGHT_ISSUE', old, new, on_ex, x) > 1.1, t
        assert price_check_side('RIGHT_ISSUE', old, new, x, now, on_ex) == 'adjusted', t
        assert price_check_side('RIGHT_ISSUE', old, new, x, raw, on_ex) == 'raw', t
    assert price_check_factor('RIGHT_ISSUE', 100, 46235, 176, 126) > 19          # FORU stays a huge action


def test_split_either_way_small_and_missing():
    assert price_check_side('STOCK_SPLIT', 1, 2, None, 422.5, 384) == 'adjusted'   # PBSA now
    assert price_check_side('STOCK_SPLIT', 1, 2, None, 845, 384) == 'raw'          # PBSA before the pull
    assert price_check_side('STOCK_SPLIT', 1, 2, None, 1000, 550) == 'raw'         # a split on a +10 % day
    assert price_check_side('BONUS_SHARE', 30, 1, None, 336, 334) is None          # PSSI 3.3 %: cannot be told
    assert price_check_side('RIGHT_ISSUE', 7, 5, None, 88, 78) is None             # no exercise price
    assert price_check_side('STOCK_SPLIT', 1, 2, None, None, 384) is None          # no close before
