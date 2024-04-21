# Use an official Python runtime as a parent image
FROM python:3.11

# Set the working directory in the container
WORKDIR /usr/src/app

# Install psycopg2 dependencies
RUN apt-get update && apt-get install -y libpq-dev gcc

# Install Python dependencies
COPY prod_requirements.txt .

RUN pip install --no-cache-dir -r prod_requirements.txt

# Copy only the necessary files
COPY src/ ./src
COPY prod.env .env

# Make port 5551 available to the world outside this container
EXPOSE 5000

# Set environment variables
ENV FLASK_APP=src/app.py
ENV FLASK_ENV=production

# Command to start the Flask application
CMD ["python", "src/app/app.py"]
