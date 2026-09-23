FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml requirements.lock ./
COPY backend ./backend
COPY evaluation ./evaluation
COPY scripts ./scripts
RUN pip install --no-cache-dir -e . -c requirements.lock
ENV CALLAI_DATASET_PATH=/data/starter_kit
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
