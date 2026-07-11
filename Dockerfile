FROM python:3.12-slim

RUN useradd --create-home --uid 10001 sandbox
WORKDIR /service

# Install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Setup the folder structure so Python can find your files
RUN mkdir app
COPY main.py search.py config.py security.py ./app/
RUN touch ./app/__init__.py

RUN chown -R sandbox:sandbox /service
USER sandbox

EXPOSE 8080
CMD python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
