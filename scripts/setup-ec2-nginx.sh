#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# setup-ec2-nginx.sh — Configura o nginx do host EC2 como proxy reverso único
# Execute uma única vez no EC2: bash scripts/setup-ec2-nginx.sh
# ─────────────────────────────────────────────────────────────────────────────
set -e

FINANCIAL_PATH="/home/ubuntu/Financial-System"
IAM_PATH="/home/ubuntu/identity-and-access-management"
NGINX_CONF="/etc/nginx/sites-available/projetos-pessoais"

echo "📦 Instalando nginx..."
sudo apt-get update -qq
sudo apt-get install -y nginx

echo "🔒 Ajustando permissões dos certificados SSL..."
sudo chmod 755 /home/ubuntu
sudo chmod 755 "$IAM_PATH"
sudo chmod 755 "$IAM_PATH/certs"
sudo chmod 644 "$IAM_PATH/certs/fullchain.pem" 2>/dev/null || true
sudo chmod 644 "$IAM_PATH/certs/privkey.pem" 2>/dev/null || true

echo "📝 Copiando configuração do nginx..."
sudo cp "$FINANCIAL_PATH/nginx/host-proxy.conf" "$NGINX_CONF"

echo "🔗 Ativando site..."
sudo ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/projetos-pessoais
sudo rm -f /etc/nginx/sites-enabled/default

echo "🧪 Testando configuração..."
sudo nginx -t

echo "🚀 Iniciando/recarregando nginx..."
sudo systemctl enable nginx
sudo systemctl restart nginx

echo ""
echo "✅ nginx configurado com sucesso!"
echo "   :80  → redirect HTTPS"
echo "   :443 → Keycloak (IAM)"
echo "   :4200 → Financial System"
