# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# Install system dependencies
# Including graphviz for the 'diagrams' library
RUN apt-get update && apt-get install -y \
    graphviz \
    build-essential \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose the API port
EXPOSE $PORT

# Define the default command to run the Python server
# Render will automatically inject the $PORT environment variable
CMD uvicorn diagram_generator.main:diagram_generator --host 0.0.0.0 --port ${PORT:-8000}
