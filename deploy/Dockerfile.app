# OCTV Python 3.12 CPU-only runtime. Reuses existing application code unchanged.
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates ffmpeg libgl1 libglib2.0-0 libgomp1 && \
    rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt /tmp/backend-requirements.txt
COPY ai/requirements.txt /tmp/ai-requirements.txt
RUN python -m pip install --upgrade pip && \
    python -m pip install -r /tmp/backend-requirements.txt -r /tmp/ai-requirements.txt
COPY . /app
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin octv && \
    chown -R octv:octv /app
USER octv
