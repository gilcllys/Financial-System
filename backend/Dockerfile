# Usa uma imagem base oficial do Python
FROM python:3.10-slim-bullseye

# Define o diretório de trabalho no container
WORKDIR /app

# Atualiza o pip e instala dependências do sistema necessárias
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && pip install --upgrade pip

# Copia o arquivo de dependências
COPY requirements.txt .

# Instala as dependências do Python
RUN pip install -r requirements.txt

# Copia o diretório financial_system explicitamente
COPY financial_system /app/financial_system

# Copia o arquivo manage.py para o diretório de trabalho
COPY financial_system/manage.py /app/manage.py

# Copia o arquivo .env para o diretório de trabalho
# COPY .env /app/.env

# Corrige permissões para garantir acesso aos arquivos
RUN chmod -R 755 /app

# Expõe a porta padrão do Django
EXPOSE 8000

# Comando padrão para rodar o servidor de desenvolvimento
CMD ["python", "/app/manage.py", "runserver", "0.0.0.0:8000"]
