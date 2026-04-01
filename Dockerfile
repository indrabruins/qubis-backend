FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY waitlist_backend.py .
COPY waitlist.db .

ENV PORT=5003
ENV WAITLIST_API_KEY=change-me-after-deploy
ENV APP_URL=https://qubis-backend.railway.app

EXPOSE 5003

CMD ["gunicorn", "--bind", "0.0.0.0:5003", "--workers", "2", "waitlist_backend:app"]
