FROM python:3.10-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    ffmpeg \
    aria2 \
    libopus0 \
    curl \
    git \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    wget \
    unzip \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# نسخ وتثبيت المتطلبات
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# تثبيت أدوات الهكر الإضافية
RUN pip install --no-cache-dir \
    holehe \
    maigret \
    h8mail \
    theHarvester \
    sherlock-project

# نسخ المشروع
COPY . .

# إنشاء المجلدات المطلوبة
RUN mkdir -p /app/data /app/sessions /app/logs /app/downloads

# المنفذ
EXPOSE 5000

# تشغيل البوت
CMD ["python", "main.py"]
