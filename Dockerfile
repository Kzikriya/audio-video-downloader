FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    redis-server \
    nginx \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directories for downloads and logs
RUN mkdir -p downloads logs

# Configure nginx
COPY nginx.conf /etc/nginx/nginx.conf

# Configure redis
COPY redis_config.conf /etc/redis/redis.conf

# Expose ports
EXPOSE 8501 6379 80

# Start script
COPY start.sh .
RUN chmod +x start.sh

CMD ["./start.sh"]