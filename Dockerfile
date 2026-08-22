# Versión fija de Python basada en slim para reducir tamaño de imagen
FROM python:3.12.13-slim

# Evitar que Python escriba archivos .pyc en disco y asegurar buffer stdout/stderr directo
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar dependencias primero para optimizar el cacheo de capas de Docker
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código fuente del proyecto
COPY . .

# Instalar el paquete en modo editable para registrar el comando CLI `agente`
RUN pip install --no-cache-dir -e .

# Comando por defecto: inicia el CLI del agente en modo chat interactivo
ENTRYPOINT ["agente"]
CMD ["chat"]
