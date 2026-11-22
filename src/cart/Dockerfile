FROM python:3.12-alpine3.23@sha256:9a7b46da82fe49a9118e0aa7e35ac3b831aa53ad4f4ebf3e16654732bc958a62 AS runtime-base
# The pinned base contains krb5-libs 1.22.1; require the patched package.
RUN apk add --no-cache 'krb5-libs>=1.22.3-r0'

FROM runtime-base AS build
WORKDIR /app
COPY requirements.lock ./
RUN pip install --only-binary=:all: --no-cache-dir --require-hashes --prefix=/install -r requirements.lock

FROM runtime-base
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
COPY --from=build /install /usr/local
COPY --chown=65532:65532 app ./app
USER 65532:65532
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=12 CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ['PORT'] + '/health', timeout=4)"
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"$PORT\""]
