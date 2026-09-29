# -*- coding: utf-8 -*-
"""الترجمة (عربي / English).

النص العربي نفسه هو مفتاح الترجمة (نفس فكرة gettext):
    _("دليل الحسابات")              → "Chart of Accounts" بالإنجليزي
    _("تم مسح {n} قيد", n=5)        → "Deleted 5 entries"
أي نص غير موجود في القاموس يظهر بالعربي كما هو — لا شيء ينكسر.

القيم المخزنة في قاعدة البيانات (أنواع الحسابات، أنواع القيود، أسماء المناطق
الافتراضية...) تبقى بالعربي، وتُترجم عند العرض فقط.
"""
import json
import os
import sys

from flask import g, has_request_context

LANGS = {"ar": {"name": "العربية", "dir": "rtl"}, "en": {"name": "English", "dir": "ltr"}}
DEFAULT_LANG = "ar"

if getattr(sys, "frozen", False):
    _BASE = sys._MEIPASS
else:
    _BASE = os.path.dirname(os.path.abspath(__file__))
_TR_DIR = os.path.join(_BASE, "translations")

_CATALOGS = {}


def _catalog(lang):
    if lang not in _CATALOGS:
        path = os.path.join(_TR_DIR, f"{lang}.json")
        try:
            with open(path, encoding="utf-8") as f:
                _CATALOGS[lang] = json.load(f)
        except FileNotFoundError:
            _CATALOGS[lang] = {}
    return _CATALOGS[lang]


def current_lang():
    if has_request_context():
        return getattr(g, "lang", DEFAULT_LANG)
    return DEFAULT_LANG


def normalize(lang):
    return lang if lang in LANGS else None


def gettext(text, lang=None, **kwargs):
    """ترجمة نص عربي للغة الحالية، مع استبدال {المتغيرات} إن وُجدت."""
    if text is None:
        return ""
    text = str(text)
    lang = lang or current_lang()
    out = text if lang == "ar" else _catalog(lang).get(text, text)
    if kwargs:
        try:
            out = out.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            pass
    return out


def js_catalog(lang):
    """قاموس اللغة كـ JSON لجافاسكربت (فارغ للعربي لأن المفتاح هو النص نفسه)."""
    return json.dumps({} if lang == "ar" else _catalog(lang), ensure_ascii=False)


_ = gettext
