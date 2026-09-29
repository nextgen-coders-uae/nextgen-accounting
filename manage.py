# -*- coding: utf-8 -*-
"""أداة إدارة نسخة عميل (تُستخدم على السيرفر — deploy/nextgen.sh بيناديها داخل الحاوية).

    python manage.py init --company "Client Co" [--admin-user admin] [--admin-name "..."] [--lang ar|en]
    python manage.py reset-password <username>
    python manage.py backup <dest.db>
    python manage.py info

كلمات المرور اللي بتطلع من هنا مؤقتة: المستخدم يُجبر على تغييرها أول ما يدخل.
"""
import argparse
import os
import secrets
import string
import sys

import config
import database as db

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def temp_password(length=12):
    """كلمة مرور عشوائية مطابقة للسياسة (حروف + أرقام) وسهلة القراءة (بدون 0/O و1/l)."""
    letters = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ"
    digits = "23456789"
    while True:
        pw = "".join(secrets.choice(letters + digits) for _ in range(length))
        if any(c in letters for c in pw) and any(c in digits for c in pw):
            return pw


def valid_username(username):
    return bool(username) and all(c in string.ascii_lowercase + string.digits + "._-" for c in username)


def initialize(company, lang="ar", admin_user="admin", admin_name=None, password=None):
    """ينشئ حساب المدير الأول وإعدادات الشركة. يرجع كلمة المرور المؤقتة."""
    password = password or temp_password()
    full_name = admin_name or ("System Administrator" if lang == "en" else "مدير النظام")
    db.create_user(admin_user, password, full_name, "admin", must_change=True)
    db.set_setting("company_name", company)
    db.set_setting("default_lang", lang)
    if lang == "en":
        db.localize_default_accounts("en")
    db.audit("system", "تهيئة نسخة العميل", company)
    return password


def bootstrap_from_env():
    """أول تشغيل على استضافة بلا أوامر (مثل Railway): لو مفيش مستخدمين، ينشئ المدير من متغيرات البيئة.

    COMPANY_NAME / DEFAULT_LANG (ar|en) / ADMIN_USERNAME / ADMIN_PASSWORD
    لو ADMIN_PASSWORD مش موجودة (أو أقل من 8 أحرف) بتتولد كلمة مؤقتة وتتكتب في سجل التشغيل (Logs).
    """
    if not config.WEB_MODE or db.query_one("SELECT id FROM users LIMIT 1"):
        return None
    company = os.environ.get("COMPANY_NAME", "").strip() or "My Company"
    lang = os.environ.get("DEFAULT_LANG", "ar").strip().lower()
    lang = lang if lang in ("ar", "en") else "ar"
    user = os.environ.get("ADMIN_USERNAME", "admin").strip().lower()
    user = user if valid_username(user) else "admin"
    given = os.environ.get("ADMIN_PASSWORD", "")
    password = initialize(company, lang, user, password=given if len(given) >= 8 else None)
    print("=" * 60, flush=True)
    print(f"NextGen Accounting: first start - admin account created for '{company}'", flush=True)
    print(f"  username: {user}", flush=True)
    if given and len(given) >= 8:
        print("  password: (the ADMIN_PASSWORD variable - temporary, must be changed at first sign-in)", flush=True)
    else:
        print(f"  password: {password}   (temporary - must be changed at first sign-in)", flush=True)
    print("=" * 60, flush=True)
    return user


def reset_from_env():
    """إعادة تعيين كلمة مرور بدون أوامر (Railway): RESET_USERNAME + RESET_PASSWORD.

    بتتطبق مرة واحدة بس لكل قيمة (بنحفظ بصمتها) — فلو المتغيرات فضلت موجودة وحصل
    إعادة تشغيل، الكلمة مش بترجع تتغير تاني. الكلمة مؤقتة والمستخدم يغيّرها أول دخول.
    """
    import hashlib
    from werkzeug.security import generate_password_hash
    user = os.environ.get("RESET_USERNAME", "").strip().lower()
    pw = os.environ.get("RESET_PASSWORD", "")
    if not config.WEB_MODE or not user or len(pw) < 8:
        return None
    mark = hashlib.sha256(f"{user}\n{pw}".encode("utf-8")).hexdigest()
    if db.get_setting("env_reset_applied") == mark:
        return None
    u = db.query_one("SELECT id FROM users WHERE username=?", (user,))
    if not u:
        print(f"NextGen Accounting: RESET_USERNAME '{user}' not found - nothing changed", flush=True)
        return None
    db.execute("UPDATE users SET password_hash=?, must_change_password=1 WHERE id=?",
               (generate_password_hash(pw), u["id"]))
    db.set_setting("env_reset_applied", mark)
    db.audit("system", "تغيير كلمة مرور", user)
    print(f"NextGen Accounting: temporary password set for '{user}' from RESET_PASSWORD "
          "(applied once - you can now delete RESET_USERNAME / RESET_PASSWORD)", flush=True)
    return user


def cmd_init(args):
    if not config.WEB_MODE:
        print("ERROR: 'init' is for web mode only (set NEXTGEN_MODE=web).")
        return 2
    db.init_db()
    if db.query_one("SELECT id FROM users LIMIT 1"):
        print("ERROR: this client is already initialized (users exist). Use reset-password instead.")
        return 2
    username = args.admin_user.strip().lower()
    if not valid_username(username):
        print("ERROR: invalid admin username (use English letters/digits).")
        return 2
    password = initialize(args.company, args.lang, username, args.admin_name)
    print("OK: client initialized")
    print(f"  company : {args.company}")
    print(f"  language: {args.lang}")
    print(f"  username: {username}")
    print(f"  password: {password}   (temporary - must be changed at first sign-in)")
    return 0


def cmd_reset(args):
    db.init_db()
    u = db.query_one("SELECT id, username FROM users WHERE username=?", (args.username.strip().lower(),))
    if not u:
        print(f"ERROR: user '{args.username}' not found")
        return 2
    password = temp_password()
    from werkzeug.security import generate_password_hash
    db.execute("UPDATE users SET password_hash=?, must_change_password=1 WHERE id=?",
               (generate_password_hash(password), u["id"]))
    db.audit("system", "تغيير كلمة مرور", u["username"])
    print(f"OK: temporary password for {u['username']}: {password}   (must be changed at first sign-in)")
    return 0


def cmd_backup(args):
    db.init_db()
    dest = db.online_backup(args.dest)
    print(f"OK: backup written to {dest} ({dest.stat().st_size:,} bytes)")
    return 0


def cmd_info(args):
    db.init_db()
    users = db.query_one("SELECT COUNT(*) AS c FROM users")["c"]
    entries = db.query_one("SELECT COUNT(*) AS c FROM journal_entries")["c"]
    print(f"mode    : {'web' if config.WEB_MODE else 'desktop'}")
    print(f"database: {db.DB_PATH}")
    print(f"company : {db.get_setting('company_name')}")
    print(f"language: {db.get_setting('default_lang') or 'ar'}")
    print(f"users   : {users}")
    print(f"entries : {entries}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="manage.py", description="NextGen Accounting — client instance management")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init", help="create the database and the first admin (web mode)")
    p.add_argument("--company", required=True)
    p.add_argument("--admin-user", default="admin")
    p.add_argument("--admin-name", default=None, help="display name (default depends on --lang)")
    p.add_argument("--lang", choices=["ar", "en"], default="ar")
    p.set_defaults(func=cmd_init)
    p = sub.add_parser("reset-password", help="set a temporary password for a user")
    p.add_argument("username")
    p.set_defaults(func=cmd_reset)
    p = sub.add_parser("backup", help="consistent online backup of the database")
    p.add_argument("dest")
    p.set_defaults(func=cmd_backup)
    p = sub.add_parser("info", help="show instance information")
    p.set_defaults(func=cmd_info)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
