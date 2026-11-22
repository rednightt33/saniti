"""EDGE multi-user Phase 1 (EXEC-MU-ACCOUNTS; CONTRACT.md section 5 "Templates"): the emails EDGE sends, one function per
purpose, in plain English (the EDGE interface language, EXEC-UI-1019B) as text plus simple HTML. Each returns
{subject, text, html}; a code email also names the code in `mask`, so the log mode can mask it.
"""
from html import escape

CODE_MINUTES = 5


def _html(paragraphs):
    body = ''.join(f'<p style="margin:0 0 14px">{p}</p>' for p in paragraphs)
    return ('<!doctype html><html><body style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;'
            f'color:#1a1a1a;max-width:520px;margin:0 auto;padding:24px">{body}'
            '<p style="margin:24px 0 0;color:#666;font-size:13px">EDGE</p></body></html>')


def _mail(subject, lines, html_lines, mask=()):
    return {'subject': subject, 'text': '\n\n'.join(lines) + '\n\nEDGE\n', 'html': _html(html_lines), 'mask': list(mask)}


def code_email(purpose, code):
    """The six-digit code of a registration, a password reset or an email change."""
    why = {'register': 'to finish creating your EDGE account',
           'reset': 'to choose a new EDGE password',
           'email_change': 'to confirm your new email address for EDGE'}[purpose]
    # the A2 fix (ERRORS M517): a code works only in the browser where it was asked for
    lines = [f'Your EDGE code is {code}.',
             f'Enter it {why}, in the browser where you asked for it. It works for {CODE_MINUTES} minutes and only once.',
             'If you did not ask for this code, you can ignore this email; nothing changes without it.']
    html = [f'Your EDGE code is <strong style="font-size:22px;letter-spacing:3px">{escape(code)}</strong>.',
            escape(lines[1]), escape(lines[2])]
    return _mail(f'Your EDGE code: {code}', lines, html, [code])


def account_exists_email():
    """Sent instead of a code when someone registers with an address that already has an account (no enumeration)."""
    lines = ['Someone (maybe you) tried to create an EDGE account with this email address, but an account already uses it.',
             'If it was you, sign in, or use "Forgot password?" on the sign-in page to choose a new password.',
             'If it was not you, you can ignore this email; your account has not changed.']
    return _mail('Your EDGE account already exists', lines, [escape(x) for x in lines])


def password_changed_email():
    """After a password change or reset: every other session was signed out."""
    lines = ['The password of your EDGE account was just changed, and every other device was signed out.',
             'If you did this, there is nothing more to do.',
             'If you did not, use "Forgot password?" on the sign-in page at once to choose a new password.']
    return _mail('Your EDGE password was changed', lines, [escape(x) for x in lines])


SUPPORT_KINDS = {'bug': 'Bug / Something not working', 'question': 'Question', 'account': 'Account or sign-in',
                 'billing': 'Billing or payment', 'feature': 'Feature request', 'data': 'Data looks wrong'}


def _one_line(text, limit):
    """A sender's text for a subject line: line breaks to spaces, cut (the header never carries a line break)."""
    return ' '.join(str(text or '').split())[:limit]


def support_email(info):
    """Phase 4, the contact-support panel (app/support.py): a sender's message to the admins, in full with its images
    attached (by reference: the sender loop reads them from edge_bff.support_attachments when it sends) and Reply going
    to the sender's address. `private`: the log mode never writes its text (it is the sender's words)."""
    sender = info.get('sender') or {}
    who = sender.get('username') or 'an account'
    kind = SUPPORT_KINDS.get(info.get('kind'), info.get('kind'))
    images = info.get('images') or []
    details = info.get('details') or {}
    head = [f"Support message #{info['ticket_id']} from {who} ({sender.get('plan') or 'no plan'}), on the {info.get('site')} site.",
            f'Type: {kind}', f"Subject: {info.get('subject')}"]
    tail = ['Technical details:\n' + '\n'.join(f'{k}: {v}' for k, v in details.items()),
            f'Images: {len(images)} attached.' if images else 'Images: none.']
    if info.get('link'):
        tail.append(f"Open it on the admin page: {info['link']}")
    if sender.get('email'):
        tail.append(f'Reply to this email to answer {who}.')
    text = '\n\n'.join(head + [info.get('body') or ''] + tail) + '\n\nEDGE\n'
    html_parts = [escape(x) for x in head]
    html_parts.append('<span style="white-space:pre-wrap">' + escape(info.get('body') or '') + '</span>')
    html_parts.append('Technical details:<br>' + '<br>'.join(f'{escape(str(k))}: {escape(str(v))}' for k, v in details.items()))
    html_parts += [escape(x) for x in tail[1:]]
    mail = {'subject': f"EDGE support #{info['ticket_id']}: {kind}: {_one_line(info.get('subject'), 120)}",
            'text': text, 'html': _html(html_parts), 'mask': [], 'private': True,
            'attachments': [{'ticket_id': int(info['ticket_id']), 'position': int(a['position']), 'filename': a['filename']}
                            for a in images]}
    if sender.get('email'):
        mail['reply_to'] = sender['email']
    return mail
