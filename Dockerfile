FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 10001 sandbox
WORKDIR /service

COPY requirements.txt ./
RUN pip install --no-cache-dir --requirement requirements.txt

RUN mkdir app
COPY config.py main.py replay.py search.py security.py ./app/
RUN touch ./app/__init__.py && chown -R sandbox:sandbox /service

USER sandbox
EXPOSE 8080

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--no-access-log", "--no-proxy-headers"]
