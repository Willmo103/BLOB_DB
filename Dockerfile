# Use an official Python runtime as a parent image
FROM python:3.11

# Set the working directory in the container
WORKDIR /usr/src/app

# Install psycopg2 dependencies
RUN apt-get update && apt-get install -y libpq-dev gcc

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy only the necessary files
COPY src/ ./src
COPY .env .

# Make port 5000 available to the world outside this container
EXPOSE 5551

# Set environment variables
ENV FLASK_APP=src/app.py
ENV FLASK_ENV=production

# Command to start the Flask application
CMD ["flask", "run" "--port=5551" "--host=0.0.0.0"]
