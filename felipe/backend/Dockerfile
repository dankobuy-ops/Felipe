FROM python:3.12-slim

WORKDIR /app

# Copy scraper modules (server.py imports from them)
COPY scraper/validate_inputs.py scraper/
COPY scraper/sheets.py scraper/

# Copy backend
COPY backend/server.py .

RUN pip install --no-cache-dir \
    google-api-python-client \
    google-auth-httplib2 \
    google-auth-oauthlib \
    requests

ENV PORT=8080
EXPOSE 8080

CMD ["python", "server.py"]
