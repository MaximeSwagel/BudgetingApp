#!/bin/bash
set -euo pipefail

dnf install -y docker
systemctl enable --now docker

mkdir -p /usr/local/lib/docker/cli-plugins
curl -sSL "https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-x86_64" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

mkdir -p /opt/budgetingapp
cd /opt/budgetingapp

DB_PASSWORD=$(aws ssm get-parameter --name "${db_ssm_param}" --with-decryption \
  --region "${aws_region}" --query "Parameter.Value" --output text)
OPENAI_API_KEY=$(aws ssm get-parameter --name "${openai_ssm_param}" --with-decryption \
  --region "${aws_region}" --query "Parameter.Value" --output text)
if [ "$OPENAI_API_KEY" = "unset" ]; then
  OPENAI_API_KEY=""
fi

cat > /opt/budgetingapp/.env <<EOF
IMAGE_TAG=latest
DATABASE_URL=postgresql+asyncpg://${db_username}:$${DB_PASSWORD}@${db_endpoint}:${db_port}/${db_name}
OPENAI_API_KEY=$${OPENAI_API_KEY}
BASE_CURRENCY=${base_currency}
EOF
chmod 600 /opt/budgetingapp/.env

cat > /opt/budgetingapp/docker-compose.yml <<'EOF'
services:
  backend:
    image: ${ecr_backend}:$${IMAGE_TAG}
    restart: unless-stopped
    environment:
      DATABASE_URL: $${DATABASE_URL}
      OPENAI_API_KEY: $${OPENAI_API_KEY}
      BASE_CURRENCY: $${BASE_CURRENCY}
    networks: [app]

  frontend:
    image: ${ecr_frontend}:$${IMAGE_TAG}
    restart: unless-stopped
    ports:
      - "80:80"
    depends_on: [backend]
    networks: [app]

networks:
  app:
    driver: bridge
EOF

aws ecr get-login-password --region "${aws_region}" | \
  docker login --username AWS --password-stdin "$(echo ${ecr_backend} | cut -d/ -f1)"

# Invoked by the GitHub Actions deploy step via `aws ssm send-command`, passed
# the new image tag (the git SHA) as $1.
cat > /opt/budgetingapp/deploy.sh <<'EOF'
#!/bin/bash
set -euo pipefail
cd /opt/budgetingapp

NEW_TAG="$1"
sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=$NEW_TAG/" .env

aws ecr get-login-password --region "${aws_region}" | \
  docker login --username AWS --password-stdin "$(echo ${ecr_backend} | cut -d/ -f1)"

docker compose pull
docker compose up -d
docker image prune -af --filter "until=168h"
EOF
chmod +x /opt/budgetingapp/deploy.sh

# First real containers land via the CI/CD deploy step (nothing pushed to ECR yet
# at boot time on a fresh account) — this just leaves the host fully ready.
