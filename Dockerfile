FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py engine_client.py gateway.py ./
COPY templates ./templates
RUN useradd --uid 1000 --create-home hub && mkdir -p /data/tasks && chown -R hub:hub /app /data && chmod -R u=rwX,go=rX /app
USER hub
EXPOSE 8000
CMD ["gunicorn","--bind","0.0.0.0:8000","--workers","1","--threads","16","--timeout","180","--graceful-timeout","190","app:app"]
