# LiveCold — AWS Deployment Guide

Deploy `tarun1948/livecold:v2` on AWS with Mosquitto MQTT broker.

---

## Option 1: EC2 (Simplest — Recommended for Hackathon)

### 1. Launch EC2 Instance

```bash
# AWS Console → EC2 → Launch Instance
# AMI: Amazon Linux 2023 or Ubuntu 22.04
# Type: t3.medium (2 vCPU, 4GB RAM — enough for demo)
# Storage: 30 GB gp3
# Security Group: Open ports 22, 1883, 5050, 8765
```

### 2. SSH & Install Docker

```bash
ssh -i your-key.pem ec2-user@<EC2-PUBLIC-IP>

# Amazon Linux 2023
sudo dnf install -y docker
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Re-login for group changes
exit
ssh -i your-key.pem ec2-user@<EC2-PUBLIC-IP>
```

### 3. Deploy

```bash
# Create project directory
mkdir livecold && cd livecold

# Create .env file with your API keys
cat > .env << 'EOF'
GOOGLE_API_KEY=your_gemini_api_key_here
GOOGLE_API_KEY_2=your_backup_key_here
MQTT_HOST=mosquitto
EOF

# Create mosquitto config
cat > mosquitto.conf << 'EOF'
listener 1883
allow_anonymous true
EOF

# Create docker-compose.yml
cat > docker-compose.yml << 'EOF'
version: "3.8"

services:
  mosquitto:
    image: eclipse-mosquitto:2
    ports:
      - "1883:1883"
    volumes:
      - ./mosquitto.conf:/mosquitto/config/mosquitto.conf
    restart: unless-stopped

  livecold:
    image: tarun1948/livecold:v2
    ports:
      - "5050:5050"
      - "8765:8765"
    env_file:
      - .env
    environment:
      - MQTT_HOST=mosquitto
    depends_on:
      - mosquitto
    restart: unless-stopped
EOF

# Pull & run
docker-compose up -d
```

### 4. Verify

```bash
# Check containers
docker-compose ps

# Check dashboard
curl http://localhost:5050/api/metrics

# Check RAG
curl -X POST http://localhost:8765/v2/answer \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What to do if temp exceeds threshold?"}'
```

**Access from browser:** `http://<EC2-PUBLIC-IP>:5050`

---

## Option 2: ECS Fargate (Serverless — Production)

### 1. Push Image to ECR (optional, can use Docker Hub directly)

```bash
aws ecr create-repository --repository-name livecold
aws ecr get-login-password | docker login --username AWS --password-stdin <ACCOUNT>.dkr.ecr.<REGION>.amazonaws.com
docker tag tarun1948/livecold:v2 <ACCOUNT>.dkr.ecr.<REGION>.amazonaws.com/livecold:v2
docker push <ACCOUNT>.dkr.ecr.<REGION>.amazonaws.com/livecold:v2
```

### 2. Create ECS Task Definition

```json
{
  "family": "livecold",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "containerDefinitions": [
    {
      "name": "mosquitto",
      "image": "eclipse-mosquitto:2",
      "portMappings": [{"containerPort": 1883}],
      "essential": true
    },
    {
      "name": "livecold",
      "image": "tarun1948/livecold:v2",
      "portMappings": [
        {"containerPort": 5050},
        {"containerPort": 8765}
      ],
      "environment": [
        {"name": "MQTT_HOST", "value": "localhost"},
        {"name": "GOOGLE_API_KEY", "value": "your_key_here"}
      ],
      "essential": true,
      "dependsOn": [{"containerName": "mosquitto", "condition": "START"}]
    }
  ]
}
```

### 3. Create ECS Service

```bash
# Create cluster
aws ecs create-cluster --cluster-name livecold-cluster

# Register task definition
aws ecs register-task-definition --cli-input-json file://task-definition.json

# Create service with ALB
aws ecs create-service \
  --cluster livecold-cluster \
  --service-name livecold-service \
  --task-definition livecold \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}"
```

---

## Option 3: Lightsail (Cheapest — $7/month)

```bash
# 1. Create Lightsail instance ($7/mo, 1GB RAM)
#    AWS Console → Lightsail → Create Instance → OS Only → Ubuntu 22.04

# 2. SSH in and install Docker (same as EC2 Step 2 but use apt)
sudo apt-get update && sudo apt-get install -y docker.io docker-compose
sudo usermod -aG docker ubuntu && newlogin

# 3. Deploy (same as EC2 Step 3)
mkdir livecold && cd livecold
# ... create .env, mosquitto.conf, docker-compose.yml (same as above)
docker-compose up -d
```

---

## Security Group / Firewall Rules

| Port | Protocol | Purpose |
|------|----------|---------|
| 22   | TCP      | SSH access |
| 1883 | TCP      | MQTT (internal only in prod) |
| 5050 | TCP      | Dashboard UI |
| 8765 | TCP      | Pathway RAG API |

> [!CAUTION]
> In production, restrict port 1883 to internal traffic only. Use HTTPS (443) with a load balancer + SSL certificate for ports 5050 and 8765.

---

## Quick Reference

```bash
# Start
docker-compose up -d

# View logs
docker-compose logs -f livecold

# Stop
docker-compose down

# Update to new image version
docker-compose pull && docker-compose up -d
```
