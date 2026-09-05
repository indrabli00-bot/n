FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Belmo uses EXPOSE as the Docker API routing source of truth.
EXPOSE 3000

# Keep liveness independent from PostgreSQL, Telegram and market data so a
# temporary upstream dependency outage cannot make the container unhealthy.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3000/', timeout=3)"

CMD ["sh","-c","uvicorn app:app --host 0.0.0.0 --port ${PORT:-3000} --workers 1"]
