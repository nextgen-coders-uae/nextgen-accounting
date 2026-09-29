# NextGen Accounting — صورة التشغيل على السيرفر (نسخة معزولة لكل عميل)
# البناء:   docker build -t nextgen-accounting .
# التشغيل:  بيتم من deploy/nextgen.sh (كل عميل حاوية لوحده + مجلد بيانات لوحده على /data)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    NEXTGEN_MODE=web \
    SMARTACCT_DB=/data \
    PORT=8000 \
    THREADS=8

# tzdata عشان التواريخ والأوقات تبقى بتوقيت العميل (متغير TZ لكل حاوية)
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# التشغيل بمستخدم عادي (مش root) — بيانات العميل كلها على /data
RUN useradd --system --uid 10001 --home-dir /data --shell /usr/sbin/nologin nextgen \
    && mkdir -p /data && chown nextgen:nextgen /data
USER nextgen

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/login', timeout=4)"

CMD ["python", "serve.py"]
