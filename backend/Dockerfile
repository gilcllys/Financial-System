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

# # Coleta arquivos estáticos (essencial para produção)
# # Certifique-se de ter STATIC_ROOT configurado no seu settings.py
RUN python financial_system/manage.py collectstatic --noinput

# Expõe a porta padrão definida no fly.toml
EXPOSE 8080

# Comando para produção usando Gunicorn
# O formato é: modulo_onde_esta_o_wsgi.wsgi:application
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--pythonpath", "financial_system", "financial_system.wsgi:application"]
