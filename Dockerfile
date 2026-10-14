FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget unzip libaio1 ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /opt/oracle && cd /opt/oracle && \
    wget -q https://download.oracle.com/otn_software/linux/instantclient/1923000/instantclient-basiclite-linux.x64-19.23.0.0.0dbru.zip && \
    unzip -q instantclient-basiclite-linux.x64-19.23.0.0.0dbru.zip && \
    rm -f instantclient-basiclite-linux.x64-19.23.0.0.0dbru.zip && \
    echo /opt/oracle/instantclient_19_23 > /etc/ld.so.conf.d/oracle.conf && \
    ldconfig

ENV ORACLE_CLIENT_LIB=/opt/oracle/instantclient_19_23
ENV LD_LIBRARY_PATH=/opt/oracle/instantclient_19_23

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

CMD gunicorn --bind 0.0.0.0:${PORT:-8080} app:app
