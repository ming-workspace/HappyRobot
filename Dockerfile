# Dockerfile
FROM python:3.9-slim
LABEL authors="ming"

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Expose both service ports
EXPOSE 8000 8001

# Command to start both services
CMD ["sh", "-c", "python verify_carrier.py & python find_available_loads.py"]