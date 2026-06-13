FROM ghcr.io/mlflow/mlflow:v2.17.2

# Install the binary psycopg2 wheel so MLflow can connect to PostgreSQL
RUN pip install --no-cache-dir psycopg2-binary==2.9.10

CMD ["mlflow", "server", "--host", "0.0.0.0", "--port", "5000"]
