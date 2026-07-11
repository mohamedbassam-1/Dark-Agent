FROM python:3.12-slim

# Create a non-root system user for safety
RUN useradd --create-home --uid 10001 sandbox

WORKDIR /service

# Copy dependency list and install them globally in the container
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application files directly from your root directory
COPY main.py search.py config.py ./

# Adjust file ownership to the sandbox user
RUN chown -R sandbox:sandbox /service

USER sandbox

EXPOSE 8080

# Start the application using Uvicorn, targeting main.py in the root
CMD python -m uvicorn main:app --host 0.0.0.0 --port $PORT
