FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app/
COPY migrations ./migrations/
COPY alembic.ini ./

RUN addgroup --system --gid 10001 orbit \
    && adduser --system --uid 10001 --ingroup orbit orbit \
    && chown -R orbit:orbit /app

USER 10001:10001

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
