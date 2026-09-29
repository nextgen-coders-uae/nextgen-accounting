# -*- coding: utf-8 -*-
"""فحص الترجمة: يطبع أي نص عربي في الواجهة ليس له ترجمة في translations/en.json.

الاستخدام (من مجلد المشروع):
    python tools/check_translations.py
يرجع كود خروج 1 لو فيه نصوص ناقصة — شغّله بعد أي تعديل في الواجهة.
"""
import ast
import glob
import json
import os
import re
import sys

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.stdout.reconfigure(encoding="utf-8")
AR = re.compile("[؀-ۿ]")


def py_string(lit):
    try:
        return ast.literal_eval(lit)
    except Exception:
        return None


keys = {}


def add(k, src):
    if k and AR.search(k):
        keys.setdefault(k, set()).add(src)


# _("..") / T("..") / _('..') in templates + JS + python
CALL = re.compile(r"""(?<![\w.])(?:_|T)\(\s*("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')""")
for f in glob.glob("templates/*.html") + ["static/js/app.js", "app.py", "excel_tools.py", "database.py"]:
    src = open(f, encoding="utf-8-sig").read()
    for m in CALL.finditer(src):
        lit = m.group(1)
        val = py_string(lit) if f.endswith(".py") else json.loads(lit) if lit.startswith('"') else lit[1:-1]
        add(val, f)
    # nav labels in base.html
    if f.endswith("base.html"):
        for m in re.finditer(r"\('/[^']*', '[\w-]+', '([^']+)'\)", src):
            add(m.group(1), f)

# values translated on display
app = open("app.py", encoding="utf-8").read()
for name in ("ROLES", "ENTRY_TYPES", "TYPE_LABELS", "BUDGET_STATUSES", "SUB_GROUP_LABELS", "PRODUCT"):
    m = re.search(rf"^{name} = ", app, re.M)
    start = m.end()
    depth, i = 0, start
    while True:
        c = app[i]
        if c in "[{(":
            depth += 1
        elif c in "]})":
            depth -= 1
            if depth == 0:
                break
        i += 1
    for s in re.findall(r'"([^"]*)"', app[start:i + 1]):
        add(s, "app.py:" + name)
for f in ("app.py", "manage.py"):
    for s in re.findall(r'db\.audit\([^,]+,\s*"([^"]+)"', open(f, encoding="utf-8").read()):
        add(s, f + ":audit")
add("إنشاء قيد ومرحلته", "app.py:audit")
add("إنشاء قيد (مسودة)", "app.py:audit")
db = open("database.py", encoding="utf-8").read()
for s in re.findall(r'"(المركز الرئيسي|المنطقة [^"]+)"', db):
    add(s, "database.py:regions")
add("أخرى", "account types")
add("حسابات عامة", "app.py")


catalog = json.load(open("translations/en.json", encoding="utf-8"))
missing = {k: sorted(v) for k, v in keys.items() if k not in catalog}
unused = [k for k in catalog if k not in keys]
for k, where in sorted(missing.items()):
    print(f"MISSING: {k!r}  <- {', '.join(where)}")
print(f"{len(keys)} texts used, {len(catalog)} translated, {len(missing)} missing, {len(unused)} unused in catalog")
sys.exit(1 if missing else 0)
