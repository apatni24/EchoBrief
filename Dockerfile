FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y nginx && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# Ensure /tmp directory exists and is writable
RUN mkdir -p /tmp && chmod 777 /tmp

# Make sure start.sh is executable
RUN chmod +x start.sh

# Copy nginx config
COPY nginx.conf /etc/nginx/nginx.conf

# Expose ports for Nginx
EXPOSE 80

CMD ["bash", "start.sh"]
