# Deploying LiveCold on AWS

Fargate task running two containers in one task definition: the Mosquitto broker
and the LiveCold application. They share the task's loopback interface, which is
why the app is configured with `MQTT_HOST=127.0.0.1`.

## Topology

```
Internet
   │
   ▼
Application Load Balancer  (:443 → :5050)
   │  health check GET /health
   ▼
ECS Fargate service  (desired count ≥ 2, spread across AZs)
   ├── container: mosquitto      :1883   (task-local broker)
   └── container: livecold       :5050 dashboard   :8765 Pathway RAG
          │
          ├── EFS volume        → /app/dashboard/data   (SQLite, survives task replacement)
          ├── Secrets Manager   → GEMINI / JWT / admin password
          └── CloudWatch Logs   → /ecs/livecold
```

## Why these choices

**Two containers, one task.** The app talks to the broker over loopback, so
there is no service discovery and no network hop. The trade-off is that the
broker scales with the app rather than independently — the moment you run more
than one task you want AWS IoT Core or a dedicated broker service instead, so
that all tasks share one message bus.

**EFS for the SQLite file.** Fargate task storage is ephemeral: a task
replacement would otherwise take the telemetry history with it. EFS keeps the
compliance record across deploys. SQLite over NFS serialises writers, which is
acceptable at one task and is the specific thing that forces a move to RDS or
Timestream when you scale out.

**OIDC instead of access keys.** `deploy-aws.yml` assumes an IAM role through
GitHub's OIDC provider, so there are no long-lived AWS credentials stored in the
repository.

**Healthcheck-gated rollout.** The deploy waits for service stability. If the new
revision's containers fail their healthcheck, ECS stops the rollout and the
previous revision keeps serving.

## One-time setup

```bash
REGION=ap-south-1
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)

# 1. Image registry
aws ecr create-repository --repository-name livecold --region "$REGION"

# 2. Secrets
aws secretsmanager create-secret --name livecold/gemini-api-key \
    --secret-string "YOUR_GEMINI_KEY" --region "$REGION"
aws secretsmanager create-secret --name livecold/jwt-secret \
    --secret-string "$(openssl rand -hex 32)" --region "$REGION"
aws secretsmanager create-secret --name livecold/super-admin-password \
    --secret-string "$(openssl rand -base64 24)" --region "$REGION"

# 3. Log group
aws logs create-log-group --log-group-name /ecs/livecold --region "$REGION"

# 4. Cluster
aws ecs create-cluster --cluster-name livecold-cluster --region "$REGION"
```

Then replace the placeholder account IDs and `fs-REPLACE_ME` in
`ecs-task-definition.json`, register it, and create the service behind an ALB.

## Repository secrets required by the workflow

| Secret | Example |
|---|---|
| `AWS_DEPLOY_ROLE_ARN` | `arn:aws:iam::123456789012:role/livecoldGithubDeploy` |
| `AWS_REGION` | `ap-south-1` |
| `ECR_REPOSITORY` | `livecold` |
| `ECS_CLUSTER` | `livecold-cluster` |
| `ECS_SERVICE` | `livecold-service` |

## Scaling beyond one task

The decision engine is a pure function of one shipment's state with no
cross-shipment joins, so it partitions cleanly by `shipment_id`. The order of
work to scale out:

1. Replace the task-local broker with **AWS IoT Core** so every task shares one
   bus, and bridge IoT Core to **MSK (Kafka)** partitioned by `shipment_id`.
2. Move per-shipment state out of process memory into **ElastiCache (Redis)**,
   keyed by shipment, so a task restart does not lose exposure counters or the
   `already_diverted` set.
3. Swap SQLite for **RDS Postgres** or **Timestream** — Timestream is the better
   fit for append-only telemetry with a retention policy.
4. Raise the ECS desired count and let each task own a Kafka partition range.
