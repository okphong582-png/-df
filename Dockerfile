FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt && useradd --create-home --uid 10001 proxy
COPY --chown=proxy:proxy settings.py proxy1.py bot.py generate_keys.py ./
COPY --chown=proxy:proxy fileinfo assembly-csharp-patch assembly-csharp-patch.gz ./
RUN chown proxy:proxy /app
USER proxy
CMD ["mitmdump", "--listen-host", "0.0.0.0", "--listen-port", "1297", "--set", "block_global=false", "--set", "connection_strategy=lazy", "--set", "confdir=/home/proxy/.mitmproxy", "-s", "proxy1.py"]
