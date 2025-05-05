#!/bin/bash

# NoSQLBench YAML Generator Run Script

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is required but not installed. Please install Python 3 and try again."
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Create yaml_files directory if it doesn't exist
if [ ! -d "yaml_files" ]; then
    echo "Creating yaml_files directory..."
    mkdir -p yaml_files
fi

# Check if NoSQLBench JAR exists, download if not
if [ ! -f "nb5.jar" ]; then
    echo "Downloading NoSQLBench JAR file..."
    # Use curl if available, otherwise try wget
    if command -v curl &> /dev/null; then
        curl -L -o nb5.jar https://github.com/nosqlbench/nosqlbench/releases/download/5.17.3/nb5.jar
    elif command -v wget &> /dev/null; then
        wget -O nb5.jar https://github.com/nosqlbench/nosqlbench/releases/download/5.17.3/nb5.jar
    else
        echo "Warning: Could not download NoSQLBench JAR. Please download it manually from:"
        echo "https://github.com/nosqlbench/nosqlbench/releases/download/5.17.3/nb5.jar"
    fi
fi

# Set environment variables
export FLASK_APP=app.py
export NB_JAR_PATH="$(pwd)/nb5.jar"

# Run the application
echo "Starting NoSQLBench YAML Generator..."
python3 app.py

# Deactivate virtual environment when done
deactivate