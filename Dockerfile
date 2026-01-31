# Use official Python image
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY weather.py .

RUN pip install --upgrade pip && \
    pip install uv && \
    pip install .

EXPOSE 8080

CMD ["uv", "run", "python", "weather.py", "--host", "0.0.0.0", "--port", "8080"]
