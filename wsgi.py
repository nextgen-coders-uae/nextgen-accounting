# -*- coding: utf-8 -*-
"""نقطة تشغيل الويب (WSGI) — يستخدمها serve.py أو أي سيرفر WSGI (waitress / gunicorn).

متغيرات البيئة:
  NEXTGEN_MODE=web      تفعيل وضع الويب (HTTPS، بدون مستخدمين افتراضيين...) — راجع config.py
  SMARTACCT_DB=/data    المجلد اللي فيه instance/ (قاعدة البيانات، المفتاح، النسخ الاحتياطية)
  SMART_BASE=...        (اختياري) مجلد الكود لو الملف ده اتنقل لمكان تاني (مثل PythonAnywhere)
"""
import os
import sys

BASE = os.environ.get("SMART_BASE") or os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import config  # noqa: E402
import database as db  # noqa: E402

if config.WEB_MODE:
    _data = os.environ.get("SMARTACCT_DB") or BASE
    try:
        os.makedirs(os.path.join(_data, "instance"), exist_ok=True)
        _probe = os.path.join(_data, "instance", ".write-test")
        open(_probe, "w").close()
        os.remove(_probe)
    except OSError as exc:
        sys.exit(f"ERROR: cannot write to the data folder {_data!r} ({exc}).\n"
                 "On Railway add the variable RAILWAY_RUN_UID=0 and attach a volume on /data.")

db.init_db()

if config.WEB_MODE:
    import manage  # noqa: E402
    manage.bootstrap_from_env()
    manage.reset_from_env()

from app import app as application  # noqa: E402
