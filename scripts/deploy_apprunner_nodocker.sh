#!/bin/bash
# ==============================================================================
# AgentHR — Deploy to AWS App Runner via Source Bundle (NO Docker required)
# Uses App Runner's managed Python 3.12 runtime with apprunner.yaml config.
# ==============================================================================
# Prerequisites (run in Mac Terminal):
#   pip3 install awscli --break-system-packages   # if aws CLI not installed
#   aws configure                                  # set your credentials
#
# Usage:
#   cd AgentHR
#   export AWS_REGION=us-east-1
#   bash scripts/deploy_apprunner_nodocker.sh
# ==============================================================================
set -e

REGION="${AWS_REGION:-us-east-1}"
SERVICE_NAME="agenthr"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ROLE_NAME="AgentHRAppRunnerRole"
BUCKET_NAME="agenthr-deploy-${ACCOUNT_ID}"
ZIP_NAME="agenthr-source.zip"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   AgentHR — App Runner Deploy (No Docker)           ║"
echo "╚══════════════════════════════════════════════════════╝"
echo "  AWS Account : ${ACCOUNT_ID}"
echo "  Region      : ${REGION}"
echo "  Method      : Source bundle via S3 (no Docker needed)"
echo ""

# ── Step 1: IAM Instance Role ──────────────────────────────────────────────
echo "▶ Step 1/5 — IAM Instance Role"
python3 scripts/create_apprunner_role.py --region "${REGION}"
ROLE_ARN=$(aws iam get-role --role-name "${ROLE_NAME}" --query "Role.Arn" --output text)
echo "  Role ARN: ${ROLE_ARN}"

# ── Step 2: Create S3 bucket for source bundle ────────────────────────────
echo ""
echo "▶ Step 2/5 — S3 Bucket"
aws s3api head-bucket --bucket "${BUCKET_NAME}" 2>/dev/null || \
  aws s3api create-bucket --bucket "${BUCKET_NAME}" --region "${REGION}" \
    $( [ "${REGION}" != "us-east-1" ] && echo "--create-bucket-configuration LocationConstraint=${REGION}" ) \
    > /dev/null
echo "  Bucket ready: s3://${BUCKET_NAME}"

# ── Step 3: Zip source code (exclude large dirs) ───────────────────────────
echo ""
echo "▶ Step 3/5 — Building Source Bundle"
rm -f "/tmp/${ZIP_NAME}"
zip -r "/tmp/${ZIP_NAME}" . \
  --exclude ".git/*" \
  --exclude ".venv/*" \
  --exclude ".venv_aws/*" \
  --exclude "venv/*" \
  --exclude "env/*" \
  --exclude "aws_env/*" \
  --exclude "__pycache__/*" \
  --exclude "*.pyc" \
  --exclude ".env" \
  --exclude "*_accessKeys.csv" \
  --exclude "website/*" \
  --exclude "sample_cvs/*" \
  --exclude "*.log" \
  -q
echo "  Source bundle created: /tmp/${ZIP_NAME}"

# Upload to S3
aws s3 cp "/tmp/${ZIP_NAME}" "s3://${BUCKET_NAME}/${ZIP_NAME}" > /dev/null
echo "  Uploaded to: s3://${BUCKET_NAME}/${ZIP_NAME}"

# ── Step 4: Configure service ─────────────────────────────────────────────
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
  \"CodeRepository\": {
    \"RepositoryUrl\": \"s3://${BUCKET_NAME}/${ZIP_NAME}\",
    \"SourceCodeVersion\": {
      \"Type\": \"BRANCH\",
      \"Value\": \"main\"
    },
    \"CodeConfiguration\": {
      \"ConfigurationSource\": \"REPOSITORY\",
      \"CodeConfigurationValues\": {
        \"Runtime\": \"PYTHON_3\",
        \"BuildCommand\": \"pip install -r requirements.txt\",
        \"StartCommand\": \"./entrypoint.sh\",
        \"Port\": \"8080\",
        \"RuntimeEnvironmentVariables\": ${ENV_VARS}
      }
    }
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
  echo "  Updating existing service..."
  aws apprunner start-deployment \
    --service-arn "${EXISTING_ARN}" \
    --region "${REGION}" > /dev/null
  SERVICE_ARN="${EXISTING_ARN}"
else
  echo "  Creating new App Runner service from source bundle..."
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
echo "║  ✅ Deployment Initiated!                            ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "  ⏳ App Runner is building (~3-5 minutes)"
echo "  Monitor: https://console.aws.amazon.com/apprunner/home?region=${REGION}#/services"
echo ""

# Poll for status
for i in $(seq 1 30); do
  STATUS=$(aws apprunner describe-service --service-arn "${SERVICE_ARN}" --region "${REGION}" \
    --query "Service.Status" --output text 2>/dev/null || echo "UNKNOWN")
  URL=$(aws apprunner describe-service --service-arn "${SERVICE_ARN}" --region "${REGION}" \
    --query "Service.ServiceUrl" --output text 2>/dev/null || echo "")

  echo "  [${i}/30] Status: ${STATUS} $([ -n "${URL}" ] && [ "${URL}" != "None" ] && echo "| URL: https://${URL}" || echo "")"

  if [ "${STATUS}" = "RUNNING" ] && [ -n "${URL}" ] && [ "${URL}" != "None" ]; then
    echo ""
    echo "┌──────────────────────────────────────────────────────┐"
    echo "│  🚀 AgentHR is LIVE!                                 │"
    echo "│                                                      │"
    echo "│  URL: https://${URL}"
    echo "│                                                      │"
    echo "│  Candidate Portal  → open URL in browser            │"
    echo "│  Recruiter Login   → hr@agenthr.ai / admin123       │"
    echo "└──────────────────────────────────────────────────────┘"
    exit 0
  fi

  if [ "${STATUS}" = "CREATE_FAILED" ] || [ "${STATUS}" = "OPERATION_FAILED" ]; then
    echo "  ❌ Deployment failed. Check App Runner console for logs."
    exit 1
  fi

  sleep 15
done
