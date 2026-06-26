FROM python:3.12-slim

WORKDIR /app

# Install deps first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Hugging Face Spaces serves the container on port 7860 (app/config.py reads
# $PORT). Other hosts that inject their own $PORT will override this.
ENV PORT=7860
# Spaces run as a non-root user; /tmp is always writable for the SQLite DB.
ENV JOBRADAR_DB=/tmp/jobradar.db
EXPOSE 7860

CMD ["python", "-m", "app.main"]
