"""Local credential bootstrap. Output is a secret: paste into Railway's secure variable editor, never Git."""
from getpass import getpass
from app.security import password_verifier
if __name__=='__main__':
    first=getpass('Private EDGE password: ')
    if len(first)<12 or first!=getpass('Repeat password: '):raise SystemExit('Passwords must match and be at least 12 characters')
    print(password_verifier(first))
