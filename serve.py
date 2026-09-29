# -*- coding: utf-8 -*-
"""سيرفر الإنتاج (Waitress) — يعمل على Linux وWindows.

    python serve.py                 → يستمع على 0.0.0.0:8000
    PORT=9000 THREADS=8 python serve.py

على السيرفر بيشتغل داخل Docker خلف Caddy (HTTPS) — راجع deploy/README.md
"""
import logging
import os

from waitress import serve

from wsgi import application

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    threads = int(os.environ.get("THREADS", "8"))
    print(f"NextGen Accounting - serving on http://{host}:{port} (threads={threads})", flush=True)
    serve(application, host=host, port=port, threads=threads,
          ident="NextGen", clear_untrusted_proxy_headers=False)
