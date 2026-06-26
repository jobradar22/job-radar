FROM python:3.12-slim

WORKDIR /app

# Install deps first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render (and most hosts) inject $PORT; app/config.py reads it.
ENV PORT=8000
EXPOSE 8000

CMD ["python", "-m", "app.main"]
