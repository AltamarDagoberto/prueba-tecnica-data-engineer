FROM python:3.12-slim

# Solo nos aseguramos de tener los certificados al día para HTTPS.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalamos las dependencias de Python primero para aprovechar la cache
COPY extractor/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Código del extractor y el schema SQL
COPY extractor/src /app/src
COPY sql /app/sql

# Corremos desde /app/src para que los imports relativos
WORKDIR /app/src

CMD ["python", "main.py"]