FROM python:3.11-slim

WORKDIR /app

# Optional: scanners used for deterministic before/after impact metrics.
# Safe to omit; the scanner degrades gracefully when tools/repo are absent.
RUN pip install --no-cache-dir pip-audit==2.7.3

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
