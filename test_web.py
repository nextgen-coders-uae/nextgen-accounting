# -*- coding: utf-8 -*-
"""اختبار وضع الويب (السيرفر) — يشغّل نسخة عميل كاملة في مجلد مؤقت ويتأكد من قواعد الأمان.

    python test_web.py

بيعمل بنفسه: manage.py init ← سيرفر الإنتاج (serve.py / Waitress) ← الاختبارات ← يقفل السيرفر.
"""
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

import requests

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("TEST_WEB_PORT", "5071"))
BASE = f"http://127.0.0.1:{PORT}"
ok_count, fail = 0, []


def check(name, cond, extra=""):
    global ok_count
    if cond:
        ok_count += 1
        print(f"  ✔ {name}")
    else:
        fail.append(name)
        print(f"  ✖ {name} {extra}")


def env_for(data_dir):
    e = dict(os.environ)
    e.update({"NEXTGEN_MODE": "web", "SMARTACCT_DB": data_dir, "PORT": str(PORT),
              "PYTHONIOENCODING": "utf-8"})
    return e


def manage(data_dir, *args):
    r = subprocess.run([sys.executable, os.path.join(HERE, "manage.py"), *args], env=env_for(data_dir),
                       capture_output=True, text=True, encoding="utf-8", stdin=subprocess.DEVNULL)
    return r.returncode, r.stdout + r.stderr


def cookie_of(resp):
    m = re.search(r"session=([^;]+)", resp.headers.get("Set-Cookie", ""))
    return m.group(1) if m else None


def get(path, sess=None, **kw):
    h = kw.pop("headers", {})
    if sess:
        h["Cookie"] = f"session={sess}"
    return requests.get(BASE + path, headers=h, allow_redirects=False, timeout=15, **kw)


def post(path, sess=None, **kw):
    h = kw.pop("headers", {})
    if sess:
        h["Cookie"] = f"session={sess}"
    return requests.post(BASE + path, headers=h, allow_redirects=False, timeout=15, **kw)


def login(user, pw, ip="10.0.0.1"):
    return post("/login", data={"username": user, "password": pw}, headers={"X-Forwarded-For": ip})


data = tempfile.mkdtemp(prefix="nextgen_web_")
server = None
try:
    print("== تهيئة نسخة عميل (manage.py init) ==")
    code, out = manage(data, "init", "--company", "Web Test Co")
    check("init نجح", code == 0, out)
    m = re.search(r"password:\s+(\S+)", out)
    temp_pw = m.group(1) if m else ""
    check("كلمة مرور مؤقتة قوية اتولدت", len(temp_pw) >= 12 and re.search(r"\d", temp_pw)
          and re.search(r"[A-Za-z]", temp_pw), out)
    code2, out2 = manage(data, "init", "--company", "X")
    check("init مرة تانية مرفوض (مايمسحش العميل)", code2 == 2, out2)

    server = subprocess.Popen([sys.executable, os.path.join(HERE, "serve.py")], env=env_for(data),
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    for _ in range(60):
        try:
            if requests.get(BASE + "/login", timeout=2).status_code == 200:
                break
        except requests.RequestException:
            time.sleep(0.5)
    check("سيرفر الإنتاج (Waitress) شغال", requests.get(BASE + "/login", timeout=5).status_code == 200)

    print("== لا توجد كلمات مرور افتراضية ==")
    for u, p in (("admin", "admin123"), ("accountant", "accountant123"), ("viewer", "viewer123")):
        r = login(u, p, ip=f"10.9.9.{len(u)}")
        check(f"الدخول بـ {u}/{p} مرفوض", r.status_code == 200 and "session=" not in r.headers.get("Set-Cookie", ""))

    print("== أول دخول: تغيير كلمة المرور إجباري ==")
    r = login("admin", temp_pw)
    sess = cookie_of(r)
    check("الدخول بالكلمة المؤقتة", r.status_code == 302 and sess)
    check("يتحول لصفحة تغيير كلمة المرور", r.headers.get("Location", "").endswith("/change-password"))
    sc = r.headers.get("Set-Cookie", "")
    check("الكوكي Secure + HttpOnly + SameSite", "Secure" in sc and "HttpOnly" in sc and "SameSite=Lax" in sc, sc)
    check("لوحة التحكم مقفولة قبل التغيير", get("/", sess).headers.get("Location", "").endswith("/change-password"))
    r = get("/api/accounts", sess)
    check("الـ API مقفول قبل التغيير (403)", r.status_code == 403 and "error" in r.json())
    check("صفحة التغيير بتفتح", get("/change-password", sess).status_code == 200)
    r = post("/change-password", sess, data={"old_password": "nope", "new_password": "Abcdef123",
                                              "confirm_password": "Abcdef123"})
    check("رفض كلمة مرور حالية غلط", r.status_code == 200 and "alert err" in r.text)
    r = post("/change-password", sess, data={"old_password": temp_pw, "new_password": "Abcdef123",
                                              "confirm_password": "Abcdef999"})
    check("رفض تأكيد غير مطابق", r.status_code == 200 and "alert err" in r.text)
    r = post("/change-password", sess, data={"old_password": temp_pw, "new_password": "abcdefgh",
                                              "confirm_password": "abcdefgh"})
    check("رفض كلمة مرور ضعيفة (بدون أرقام)", r.status_code == 200 and "alert err" in r.text)
    r = post("/change-password", sess, data={"old_password": temp_pw, "new_password": "Admin2026x",
                                              "confirm_password": "Admin2026x"})
    check("تغيير كلمة المرور نجح", r.status_code == 302 and r.headers.get("Location", "").endswith("/"))
    r = get("/", sess)
    check("لوحة التحكم اتفتحت بعد التغيير", r.status_code == 200 and "Web Test Co" in r.text)
    check("الكلمة المؤقتة ماعادتش شغالة", "session=" not in login("admin", temp_pw, "10.0.0.2").headers.get("Set-Cookie", ""))
    r = login("admin", "Admin2026x", "10.0.0.3")
    sess = cookie_of(r)
    check("الدخول بالكلمة الجديدة مباشرة للوحة", r.status_code == 302 and r.headers.get("Location", "").endswith("/"))

    print("== HTTPS والهيدرز ==")
    r = get("/login", headers={"X-Forwarded-Proto": "https"})
    check("HSTS موجود خلف HTTPS", "max-age" in r.headers.get("Strict-Transport-Security", ""))
    check("HSTS مش موجود على http", "Strict-Transport-Security" not in get("/login").headers)
    r = get("/lang/en?next=/login")
    check("كوكي اللغة Secure", "Secure" in r.headers.get("Set-Cookie", ""))

    print("== الحماية من التخمين بعنوان العميل الحقيقي ==")
    for i in range(5):
        login(f"ghost{i}", "bad-password", ip="203.0.113.7")
    r = login("ghost9", "bad-password", ip="203.0.113.7")
    check("العنوان المهاجم اتحظر بعد 5 محاولات", "5" in r.text and "alert err" in r.text and "حظر" in r.text)
    r = login("admin", "Admin2026x", ip="198.51.100.20")
    check("مستخدم من عنوان تاني مايتأثرش", r.status_code == 302)
    for i in range(10):
        login("victim", "bad-password", ip=f"192.0.2.{i + 1}")
    r = login("victim", "bad-password", ip="192.0.2.99")
    check("حظر اسم المستخدم بعد 10 محاولات من عناوين مختلفة", "حظر" in r.text)

    print("== المستخدمين اللي المدير بيضيفهم ==")
    r = post("/api/users", sess, json={"username": "sara", "full_name": "Sara", "role": "accountant",
                                        "password": "Sara12345"})
    check("المدير أضاف مستخدم", r.status_code == 200, r.text[:120])
    r = login("sara", "Sara12345", "10.1.1.1")
    check("المستخدم الجديد لازم يغيّر كلمة المرور", r.headers.get("Location", "").endswith("/change-password"))
    uid = sqlite3.connect(os.path.join(data, "instance", "accounting.db")).execute(
        "SELECT id FROM users WHERE username='sara'").fetchone()[0]
    s2 = cookie_of(r)
    post("/change-password", s2, data={"old_password": "Sara12345", "new_password": "Sara2026ok",
                                        "confirm_password": "Sara2026ok"})
    r = post(f"/api/users/{uid}/password", sess, json={"password": "Reset12345"})
    check("المدير عمل إعادة تعيين", r.status_code == 200)
    r = login("sara", "Reset12345", "10.1.1.2")
    check("بعد إعادة التعيين لازم يغيّر تاني", r.headers.get("Location", "").endswith("/change-password"))
    r = get("/users", sess)
    check("صفحة المستخدمين بتعرض رابط الموقع مش IP:5000", "IP-" not in r.text and BASE in r.text)

    print("== أدوات السيرفر (manage.py) ==")
    code, out = manage(data, "reset-password", "admin")
    m = re.search(r"admin:\s+(\S+)", out)
    check("reset-password طلّع كلمة مؤقتة", code == 0 and m, out)
    if m:
        r = login("admin", m.group(1), "10.2.2.2")
        check("الكلمة المؤقتة شغالة وتجبر على التغيير", r.headers.get("Location", "").endswith("/change-password"))
    dest = os.path.join(data, "export", "backup-test.db")
    code, out = manage(data, "backup", dest)
    ok_db = False
    if code == 0 and os.path.exists(dest):
        c = sqlite3.connect(dest)
        ok_db = c.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and \
            c.execute("SELECT COUNT(*) FROM users").fetchone()[0] >= 2
        c.close()
    check("backup بيطلّع نسخة سليمة وهو شغال", ok_db, out)
    code, out = manage(data, "info")
    check("info", code == 0 and "mode    : web" in out, out)

    print("== عميل بالإنجليزي من أول يوم ==")
    data_en = tempfile.mkdtemp(prefix="nextgen_web_en_")
    code, out = manage(data_en, "init", "--company", "Gulf Co", "--lang", "en")
    c = sqlite3.connect(os.path.join(data_en, "instance", "accounting.db"))
    cash = c.execute("SELECT name FROM accounts WHERE acc_no='1101'").fetchone()[0]
    admin_name = c.execute("SELECT full_name FROM users WHERE username='admin'").fetchone()[0]
    lang = c.execute("SELECT value FROM settings WHERE key='default_lang'").fetchone()[0]
    c.close()
    check("init --lang en: الحسابات والواجهة بالإنجليزي", code == 0 and cash == "Cash on hand" and lang == "en",
          f"{cash} / {lang}")
    check("init --lang en: اسم المدير بالإنجليزي", admin_name == "System Administrator", admin_name)
    shutil.rmtree(data_en, ignore_errors=True)
finally:
    if server:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
    time.sleep(0.5)
    shutil.rmtree(data, ignore_errors=True)

def start_server(data_dir, extra_env):
    e = env_for(data_dir)
    e.update(extra_env)
    log = open(os.path.join(data_dir, "server-out.log"), "w", encoding="utf-8")
    p = subprocess.Popen([sys.executable, os.path.join(HERE, "serve.py")], env=e, stdout=log,
                         stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    for _ in range(60):
        try:
            if requests.get(BASE + "/login", timeout=2).status_code == 200:
                break
        except requests.RequestException:
            time.sleep(0.5)
    return p, log


def stop_server(p, log):
    p.terminate()
    try:
        p.wait(timeout=10)
    except subprocess.TimeoutExpired:
        p.kill()
    log.close()
    time.sleep(0.5)


print("== أول تشغيل على استضافة بدون أوامر (Railway) ==")
boot = tempfile.mkdtemp(prefix="nextgen_boot_")
try:
    env_vars = {"COMPANY_NAME": "Railway Test Co", "DEFAULT_LANG": "en", "ADMIN_PASSWORD": "Start2026abc"}
    p, log = start_server(boot, env_vars)
    r = login("admin", "Start2026abc", ip="198.51.100.77")
    s3 = cookie_of(r)
    check("المدير اتعمل من متغيرات البيئة", r.status_code == 302 and s3)
    check("وبرضه لازم يغيّر الكلمة أول دخول", r.headers.get("Location", "").endswith("/change-password"))
    post("/change-password", s3, data={"old_password": "Start2026abc", "new_password": "Boot2026ok",
                                        "confirm_password": "Boot2026ok"})
    r = get("/", s3)
    check("اسم الشركة ولغة البداية من المتغيرات", "Railway Test Co" in r.text and 'lang="en"' in r.text)
    r = get("/audit", s3)
    check("سجل العمليات بيسجل عنوان الزائر الحقيقي", "198.51.100.77" in r.text)
    stop_server(p, log)
    p, log = start_server(boot, dict(env_vars, ADMIN_PASSWORD="Another2026x"))
    c = sqlite3.connect(os.path.join(boot, "instance", "accounting.db"))
    n_users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    c.close()
    check("إعادة التشغيل مابتعملش مدير تاني ولا بتغيّر كلمته", n_users == 1 and
          "session=" not in login("admin", "Another2026x", "198.51.100.78").headers.get("Set-Cookie", ""))
    stop_server(p, log)
    reset_env = dict(env_vars, RESET_USERNAME="admin", RESET_PASSWORD="Recover2026z")
    p, log = start_server(boot, reset_env)
    r = login("admin", "Recover2026z", "198.51.100.79")
    s4 = cookie_of(r)
    check("RESET_PASSWORD من إعدادات الاستضافة شغالة ومؤقتة", r.headers.get("Location", "").endswith("/change-password"))
    post("/change-password", s4, data={"old_password": "Recover2026z", "new_password": "Final2026ok",
                                        "confirm_password": "Final2026ok"})
    stop_server(p, log)
    p, log = start_server(boot, reset_env)
    r = login("admin", "Final2026ok", "198.51.100.80")
    check("إعادة التشغيل بنفس المتغيرات مابترجعش تغيّر الكلمة", r.status_code == 302 and
          r.headers.get("Location", "").endswith("/"))
    stop_server(p, log)
finally:
    shutil.rmtree(boot, ignore_errors=True)

boot2 = tempfile.mkdtemp(prefix="nextgen_boot2_")
try:
    p, log = start_server(boot2, {"COMPANY_NAME": "No Password Co"})
    stop_server(p, log)
    out = open(os.path.join(boot2, "server-out.log"), encoding="utf-8").read()
    m = re.search(r"password:\s+(\S+)\s+\(temporary", out)
    check("بدون ADMIN_PASSWORD: كلمة مؤقتة بتظهر في الـ Logs", bool(m), out[-300:])
    if m:
        p, log = start_server(boot2, {"COMPANY_NAME": "No Password Co"})
        r = login("admin", m.group(1), "198.51.100.90")
        check("والكلمة اللي في الـ Logs شغالة", r.headers.get("Location", "").endswith("/change-password"))
        stop_server(p, log)
finally:
    shutil.rmtree(boot2, ignore_errors=True)

print("=" * 46)
if fail:
    print(f"فشل {len(fail)} اختبار: {fail}")
    sys.exit(1)
print(f"كل اختبارات وضع الويب نجحت ({ok_count}) ✔")
