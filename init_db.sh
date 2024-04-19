#!/bin/bash

set -e

# Wait for the Postgres server to become available.
echo "Waiting for postgres..."

while ! pg_isready -q -h $DB_HOST -p $DB_PORT -U $DB_USER
do
  echo "$(date) - waiting for database to start"
  sleep 2
done

# Run the SQL script to create the `scripts` table.
cat << EOF | psql -v ON_ERROR_STOP=1 --username "$DB_USER" --dbname "$DB_NAME" --host "$DB_HOST"
CREATE TABLE IF NOT EXISTS scripts (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255),
    data BYTEA,
    mimetype VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
EOF
echo "Database initialized successfully."

# Hand off to the CMD of the Dockerfile
# exec "$@"
