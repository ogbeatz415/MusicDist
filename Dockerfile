FROM python:3.12-slim-bookworm AS common
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements-lock.txt .
RUN pip install --no-cache-dir -r requirements-lock.txt
COPY musicdist ./musicdist
COPY static ./static
RUN useradd --uid 10001 --create-home musicdist && mkdir -p /app/data && chown musicdist /app/data
USER musicdist
EXPOSE 8080
CMD ["uvicorn", "musicdist.api:app", "--host", "0.0.0.0", "--port", "8080"]
