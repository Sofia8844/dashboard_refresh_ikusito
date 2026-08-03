# Stage 1: construye el entorno Python aislado con las dependencias instaladas.
FROM python:3.12-slim AS builder

# Evita escribir .pyc y fuerza logs sin buffer para verlos en Docker.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Crea un virtualenv que luego se copiara al stage runtime.
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Instala el paquete dentro del virtualenv usando la metadata del proyecto.
RUN python -m venv /opt/venv
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --no-cache-dir .

# Stage 2: imagen final mas limpia para ejecutar API, worker o migraciones.
FROM python:3.12-slim AS runtime

# Mantiene el comportamiento de logs/bytecode en el contenedor final.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Activa el virtualenv copiado desde builder.
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Copia dependencias ya instaladas y el codigo necesario en runtime.
COPY --from=builder /opt/venv /opt/venv
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations
COPY app ./app
COPY worker.py ./worker.py

# Comando por defecto: levanta la API. Docker Compose lo sobreescribe para worker/migrate.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
