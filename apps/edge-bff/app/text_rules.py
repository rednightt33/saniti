"""EXEC-MU-ACCOUNTS fix round (re-check R2-18; CONTRACT.md sections 1 and 10): the rule for a person's name, free text
that one account types and another (the Phase 4 admin list, detail and audit; later receipts and emails) reads.

- **At registration** (`person_name`): the name is stored in Unicode NFC (the same name typed on two keyboards is one
  name; NFKC is not used, it can change a legitimate name), with runs of white space as one space and none at the ends,
  1 to 100 characters. Refused, with the field and a sentence that says what to change (AGENTS.md "Gates and evidence"
  (d)): a control character (category Cc), an invisible format character (Cf: the bidi overrides and isolates that can
  make "nimda" read as "admin", zero-width spaces, the byte-order mark) except the zero-width joiner and non-joiner some
  scripts need (U+200D, U+200C), a line or paragraph separator, a private-use, surrogate or unassigned code point, and
  the markup characters < and >.
- **On display**: a name is shown as text, never as markup (the shell's element() builds text nodes; a page that sets
  innerHTML escapes it). In a file a spreadsheet opens (CSV, XLSX), a cell that starts with = + - @ (or a tab or a
  carriage return) is written with a leading apostrophe (`export_cell`), so it is never read as a formula.
"""
import unicodedata

NAME_MAX = 100
JOINERS = frozenset({'\u200c', '\u200d'})      # zero-width non-joiner and joiner (some scripts and emoji need them)
REFUSED_CATEGORIES = frozenset({'Cc', 'Cf', 'Cs', 'Co', 'Cn', 'Zl', 'Zp'})
MARKUP = frozenset('<>')
FORMULA_START = ('=', '+', '-', '@', '\t', '\r')


def name_problem(text):
    """The sentence that says what to change in a name, or '' when it may be stored (text already normalised)."""
    if not 1 <= len(text) <= NAME_MAX:
        return f'Enter 1 to {NAME_MAX} characters.'
    for ch in text:
        if ch in MARKUP:
            return 'Remove the characters < and > from the name.'
        if ch not in JOINERS and unicodedata.category(ch) in REFUSED_CATEGORIES:
            return ('Remove the hidden or control character from the name (it may come from copying the name from '
                    'another page); type the name again.')
    return ''


def person_name(value):
    """(name, problem): the name as stored (NFC, one space between words) and '' , or the problem sentence."""
    text = ' '.join(unicodedata.normalize('NFC', value if isinstance(value, str) else '').split())
    return text, name_problem(text)


# Phase 4, the contact-support panel (app/support.py): in free text a person writes to EDGE (a support message) the
# characters that hide, reverse or break the text it shows: controls (Cc), invisible format characters (Cf: the bidi
# overrides and isolates, zero-width spaces, the byte-order mark) but the joiners, lone surrogates (Cs, which no
# database or email can carry), line and paragraph separators. Private-use and not yet assigned code points (Co, Cn) are
# kept there, unlike in a name: a new emoji is unassigned for this Python until its Unicode version catches up.
HIDDEN_CATEGORIES = frozenset({'Cc', 'Cf', 'Cs', 'Zl', 'Zp'})


def is_hidden(ch, allow=''):
    """True for a character of HIDDEN_CATEGORIES that is not a joiner and not one of `allow` (e.g. '\n\t')."""
    return ch not in allow and ch not in JOINERS and unicodedata.category(ch) in HIDDEN_CATEGORIES


def hidden_character(text, allow=''):
    """True when the text holds a hidden or control character (is_hidden)."""
    return any(is_hidden(ch, allow) for ch in text)


def without_hidden(text, allow=''):
    """The text without its hidden and control characters (for what EDGE only records, e.g. a browser's name)."""
    return ''.join(ch for ch in text if not is_hidden(ch, allow))


def export_cell(value):
    """A text value as written into a file a spreadsheet opens: a leading = + - @ (or tab, carriage return) is
    preceded by an apostrophe, so the cell is text, never a formula."""
    text = '' if value is None else str(value)
    return "'" + text if text.startswith(FORMULA_START) else text
