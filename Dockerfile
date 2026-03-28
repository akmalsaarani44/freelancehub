# Use a slim Python 3.11 base image
FROM python:3.11-slim

# Set working directory inside the container
WORKDIR /app

# Install system dependencies needed for psycopg2
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose port 8080 (Fly.io default)
EXPOSE 8080

# Start gunicorn with 2 workers on port 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "120", "app:app"]
