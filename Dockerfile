FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# نسخ جميع ملفات المشروع
COPY . .

EXPOSE 5000

# التشغيل عبر main.py لتهيئة الحلقة الأساسية والبوت
CMD ["python", "main.py"]
