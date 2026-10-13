FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt && useradd --create-home --uid 10001 ffruntime
COPY --chown=ffruntime:ffruntime settings.py proxy_accounts.py proxy1.py bot.py generate_keys.py ./
COPY --chown=ffruntime:ffruntime fileinfo assembly-csharp-patch assembly-csharp-patch.gz ./
RUN mkdir -p /home/ffruntime/.mitmproxy && chown -R ffruntime:ffruntime /app /home/ffruntime/.mitmproxy
USER ffruntime
CMD ["mitmdump", "--listen-host", "0.0.0.0", "--listen-port", "1297", "--set", "block_global=false", "--set", "connection_strategy=lazy", "--set", "confdir=/home/ffruntime/.mitmproxy", "-s", "proxy1.py"]
