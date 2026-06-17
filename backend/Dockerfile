# # Usa uma imagem base oficial do Python
# FROM python:3.10-slim-bullseye

# # Define o diretório de trabalho no container
# WORKDIR /app

# # Atualiza o pip e instala dependências do sistema necessárias
# RUN apt-get update \
#     && apt-get install -y --no-install-recommends gcc libpq-dev \
#     && pip install --upgrade pip

# # Copia todo o conteúdo da pasta backend para o diretório de trabalho
# COPY . /app

# # Corrige permissões para garantir acesso aos arquivos
# RUN chmod -R 755 /app

# # Instala as dependências do Python
# RUN pip install --no-cache-dir -r /app/requirements.txt

# # Expõe a porta padrão do Django
# EXPOSE 8000

# # Comando padrão para rodar o servidor de desenvolvimento
# CMD ["python", "/app/financial_system/manage.py", "runserver", "0.0.0.0:8000"]

# Usa uma imagem base oficial do Python
FROM python:3.10-slim-bullseye

# Define o diretório de trabalho no container
WORKDIR /app

# Variáveis de ambiente para Python não gerar arquivos .pyc e exibir logs em tempo real
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Atualiza o pip e instala dependências do sistema necessárias para o Postgres e compilação
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --upgrade pip

# Copia os arquivos de dependências primeiro (otimiza o cache do Docker)
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir gunicorn  # Garante que o gunicorn esteja instalado

# Copia todo o conteúdo da pasta backend para o diretório de trabalho
COPY . /app

# Corrige permissões para garantir acesso aos arquivos
RUN chmod -R 755 /app

# Coleta arquivos estáticos (essencial para produção)
# SECRET_KEY dummy para permitir collectstatic durante o build
ARG SECRET_KEY=dummy-build-key
ENV SECRET_KEY=${SECRET_KEY}
RUN python financial_system/manage.py collectstatic --noinput

# Expõe a porta padrão definida no fly.toml
EXPOSE 8080

# Número de workers: (2 * vCPU) + 1
#   t3.micro (1 vCPU) → 3 workers
#   t3.small (2 vCPU) → 5 workers
# Sobrescreva via env GUNICORN_WORKERS no docker-compose ou ECS task definition.
ENV GUNICORN_WORKERS=3

# Comando para produção usando Gunicorn otimizado para EC2
# --max-requests / --max-requests-jitter: recicla workers periodicamente,
#   evitando vazamentos de memória em processos de longa duração.
# --keepalive: reutiliza conexões TCP entre Nginx e Gunicorn (ou ALB).
# --timeout: mata worker travado após 30s (evita starvation de slots).
CMD ["sh", "-c", \
     "gunicorn \
     --bind 0.0.0.0:8080 \
     --workers ${GUNICORN_WORKERS} \
     --worker-class sync \
     --worker-connections 1000 \
     --timeout 30 \
     --keepalive 5 \
     --max-requests 1000 \
     --max-requests-jitter 100 \
     --pythonpath financial_system \
     --access-logfile - \
     --error-logfile - \
     financial_system.wsgi:application"]
