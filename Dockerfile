FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir . && \
    useradd --uid 10001 --create-home receptionist && \
    mkdir -p /data && chown receptionist:receptionist /data
USER receptionist
ENV VD_DB_PATH=/data/voicedesk.sqlite
EXPOSE 8000
CMD ["uvicorn","voicedesk.api:app","--host","0.0.0.0","--port","8000"]
