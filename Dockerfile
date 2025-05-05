FROM python:3.9-slim

WORKDIR /app

# Install Java for NoSQLBench
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    openjdk-17-jre-headless \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Download NoSQLBench
RUN curl -L -o nb5.jar https://github.com/nosqlbench/nosqlbench/releases/download/5.17.3/nb5.jar

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directory for YAML files
RUN mkdir -p yaml_files

# Expose port
EXPOSE 6000

# Set environment variables
ENV FLASK_APP=app.py
ENV NB_JAR_PATH=/app/nb5.jar

# Run the application with Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]