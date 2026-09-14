#!/bin/bash
# ==============================================================================
# AgentHR — Deploy to AWS App Runner (with ECR + IAM Instance Role)
# ==============================================================================
# Usage:
#   cd AgentHR
#   export AWS_REGION=us-east-1   # optional, defaults to us-east-1
#   bash scripts/deploy_apprunner.sh
# ==============================================================================
set -e

REGION="${AWS_REGION:-us-east-1}"
SERVICE_NAME="agenthr"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${SERVICE_NAME}"
ROLE_NAME="AgentHRAppRunnerRole"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║      AgentHR — AWS App Runner Deployment             ║"
echo "╚══════════════════════════════════════════════════════╝"
echo "  AWS Account : ${ACCOUNT_ID}"
echo "  Region      : ${REGION}"
echo "  ECR Repo    : ${ECR_REPO}"
echo "  Service     : ${SERVICE_NAME}"
echo ""

# ── Step 1: Create / verify IAM Instance Role ──────────────────────────────
echo "▶ Step 1/5 — IAM Instance Role"
python3 scripts/create_apprunner_role.py --region "${REGION}"
ROLE_ARN=$(aws iam get-role --role-name "${ROLE_NAME}" --query "Role.Arn" --output text)
echo "  Role ARN: ${ROLE_ARN}"

# ── Step 2: Create ECR repository (idempotent) ─────────────────────────────
echo ""
echo "▶ Step 2/5 — ECR Repository"
aws ecr describe-repositories --repository-names "${SERVICE_NAME}" --region "${REGION}" > /dev/null 2>&1 \
  || aws ecr create-repository --repository-name "${SERVICE_NAME}" --region "${REGION}" > /dev/null
echo "  ECR repository ready: ${ECR_REPO}"

# ── Step 3: Docker login, build, push ─────────────────────────────────────
echo ""
echo "▶ Step 3/5 — Docker Build & Push"
aws ecr get-login-password --region "${REGION}" \
  | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

echo "  Building Docker image (this takes ~2 minutes)..."
docker build --platform linux/amd64 -t "${SERVICE_NAME}:latest" .
docker tag "${SERVICE_NAME}:latest" "${ECR_REPO}:latest"

echo "  Pushing image to ECR..."
docker push "${ECR_REPO}:latest"
echo "  Image pushed: ${ECR_REPO}:latest"

# ── Step 4: Build environment variable JSON for App Runner ─────────────────
echo ""
echo "▶ Step 4/5 — Configuring App Runner Service"

ENV_VARS='[
  {"Name":"STORE_BACKEND","Value":"dynamodb"},
  {"Name":"DYNAMODB_TABLE_PREFIX","Value":"agenthr_"},
  {"Name":"LLM_BACKEND","Value":"bedrock"},
  {"Name":"BEDROCK_MODEL_ID","Value":"us.amazon.nova-pro-v1:0"},
  {"Name":"AWS_REGION","Value":"'"${REGION}"'"},
  {"Name":"AGENT_AUTONOMOUS","Value":"1"},
  {"Name":"ENABLE_APPROVAL_GATE","Value":"1"},
  {"Name":"APP_HOST","Value":"0.0.0.0"},
  {"Name":"APP_PORT","Value":"8000"},
  {"Name":"ADMIN_EMAIL","Value":"hr@agenthr.ai"},
  {"Name":"ADMIN_PASSWORD","Value":"admin123"},
  {"Name":"SECRET_KEY","Value":"agenthr-prod-secret-change-me"}
]'

SOURCE_CONFIG="{
  \"ImageRepository\": {
    \"ImageIdentifier\": \"${ECR_REPO}:latest\",
    \"ImageConfiguration\": {
      \"Port\": \"8080\",
      \"RuntimeEnvironmentVariables\": ${ENV_VARS}
    },
    \"ImageRepositoryType\": \"ECR\"
  },
  \"AutoDeploymentsEnabled\": false
}"

INSTANCE_CONFIG="{
  \"Cpu\": \"1024\",
  \"Memory\": \"2048\",
  \"InstanceRoleArn\": \"${ROLE_ARN}\"
}"

# ── Step 5: Create or update App Runner service ────────────────────────────
echo ""
echo "▶ Step 5/5 — App Runner Service"
EXISTING_ARN=$(aws apprunner list-services --region "${REGION}" \
  --query "ServiceSummaryList[?ServiceName=='${SERVICE_NAME}'].ServiceArn" \
  --output text 2>/dev/null || echo "")

if [ -n "${EXISTING_ARN}" ] && [ "${EXISTING_ARN}" != "None" ]; then
  echo "  Updating existing App Runner service..."
  aws apprunner update-service \
    --service-arn "${EXISTING_ARN}" \
    --source-configuration "${SOURCE_CONFIG}" \
    --instance-configuration "${INSTANCE_CONFIG}" \
    --region "${REGION}" > /dev/null
  SERVICE_ARN="${EXISTING_ARN}"
else
  echo "  Creating new App Runner service..."
  SERVICE_ARN=$(aws apprunner create-service \
    --service-name "${SERVICE_NAME}" \
    --source-configuration "${SOURCE_CONFIG}" \
    --instance-configuration "${INSTANCE_CONFIG}" \
    --region "${REGION}" \
    --query "Service.ServiceArn" \
    --output text)
fi

echo ""
echo "  Service ARN: ${SERVICE_ARN}"
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  ✅ Deployment Initiated Successfully!               ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "  ⏳ App Runner is building and deploying (~3-5 minutes)"
echo ""
echo "  Monitor progress:"
echo "  https://console.aws.amazon.com/apprunner/home?region=${REGION}#/services"
echo ""
echo "  Your live URL will be shown as the 'Default domain' once status = Running."
echo "  Format: https://xxxxxxxx.${REGION}.awsapprunner.com"
echo ""

# Wait and poll for the service URL
echo "  Polling for service URL (press Ctrl+C to stop waiting and check console manually)..."
for i in $(seq 1 30); do
  STATUS=$(aws apprunner describe-service --service-arn "${SERVICE_ARN}" --region "${REGION}" \
    --query "Service.Status" --output text 2>/dev/null || echo "UNKNOWN")
  URL=$(aws apprunner describe-service --service-arn "${SERVICE_ARN}" --region "${REGION}" \
    --query "Service.ServiceUrl" --output text 2>/dev/null || echo "")

  echo "  [${i}/30] Status: ${STATUS} $([ -n "${URL}" ] && echo "| URL: https://${URL}" || echo "")"

  if [ "${STATUS}" = "RUNNING" ] && [ -n "${URL}" ]; then
    echo ""
    echo "┌──────────────────────────────────────────────────────┐"
    echo "│  🚀 AgentHR is LIVE!                                 │"
    echo "│                                                      │"
    echo "│  URL: https://${URL}"
    echo "│                                                      │"
    echo "│  Candidate Portal  → open URL in browser            │"
    echo "│  Recruiter Login   → hr@agenthr.ai / admin123       │"
    echo "└──────────────────────────────────────────────────────┘"
    break
  fi

  if [ "${STATUS}" = "CREATE_FAILED" ] || [ "${STATUS}" = "OPERATION_FAILED" ]; then
    echo "  ❌ Deployment failed. Check logs in App Runner console."
    exit 1
  fi

  sleep 15
done
