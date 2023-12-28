# Stage 1: Build
FROM amd64/python:3.9.13-bullseye as build

COPY requirements.txt requirements.txt

RUN pip install -r requirements.txt

# Stage 2: Runtime
FROM amd64/python:3.9.13-slim-bullseye

WORKDIR /usr/src/app

COPY --from=build /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages

COPY --from=build /usr/local/bin /usr/local/bin

COPY main.py .
COPY app_metadata.py .
COPY __init__.py .

EXPOSE 8080

CMD ["uvicorn", "main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "8080"]
