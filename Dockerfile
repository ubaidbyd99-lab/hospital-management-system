FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget unzip libaio1 ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /opt/oracle && cd /opt/oracle && \
    wget -q https://download.oracle.com/otn_software/linux/instantclient/2390000/instantclient-basic-linux.x64-23.9.0.25.07.zip && \
    unzip -q instantclient-basic-linux.x64-23.9.0.25.07.zip && \
    rm -f instantclient-basic-linux.x64-23.9.0.25.07.zip

ENV ORACLE_CLIENT_LIB=/opt/oracle/instantclient_23_9
ENV LD_LIBRARY_PATH=/opt/oracle/instantclient_23_9

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

CMD gunicorn --bind 0.0.0.0:${PORT:-8080} app:app
