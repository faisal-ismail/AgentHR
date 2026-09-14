# ☁️ AgentHR — AWS Cloud Setup & Deployment Guide

This guide walks you step-by-step through setting up credentials from your **AWS Console account**, enabling **Amazon Bedrock Foundation Models**, provisioning **Amazon DynamoDB**, and deploying **AgentHR** live to AWS using **AWS App Runner** and **Amazon Bedrock AgentCore Runtime**.

---

## 📑 Table of Contents

1. [Architecture & Deployment Overview](#1-architecture--deployment-overview)
2. [Step 1: Create IAM User & Get AWS Credentials](#step-1-create-iam-user--get-aws-credentials)
3. [Step 2: Enable Amazon Nova Model Access in Bedrock](#step-2-enable-amazon-nova-model-access-in-bedrock)
4. [Step 3: Configure AWS Credentials on Your Machine](#step-3-configure-aws-credentials-on-your-machine)
5. [Step 4: Provision Amazon DynamoDB Tables](#step-4-provision-amazon-dynamodb-tables)
6. [Step 5: Deploy to AWS App Runner (Live Public URL)](#step-5-deploy-to-aws-app-runner-live-public-url)
7. [Step 6: Deploy to Amazon Bedrock AgentCore Runtime](#step-6-deploy-to-amazon-bedrock-agentcore-runtime)
8. [Step 7: Verify the Live Deployment](#step-7-verify-the-live-deployment)
9. [Step 8: Cost Optimization & Teardown (Keep Costs $0)](#step-8-cost-optimization--teardown-keep-costs-0)
10. [Troubleshooting & FAQs](#troubleshooting--faqs)

---

## 1. Architecture & Deployment Overview

```
                          [ Candidate / Recruiter Browser ]
                                         │
                                         ▼ (Public HTTPS)
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             AWS App Runner Service                               │
│                                                                                  │
│   ┌────────────────────────────────┐    ┌───────────────────────────────────┐    │
│   │   Streamlit Frontend (:8080)   │───▶│   FastAPI + AgentCore (:8000)     │    │
│   │   • Candidate Careers Portal   │    │   • POST /invocations & GET /ping │    │
│   │   • Recruiter Action Approvals │    │   • Strands Agents Coordinator    │    │
│   └────────────────────────────────┘    └─────────────────┬─────────────────┘    │
└───────────────────────────────────────────────────────────┼──────────────────────┘
                                                            │
                            ┌───────────────────────────────┴─────────────────┐
                            ▼                                                 ▼
               ┌───────────────────────────┐                     ┌───────────────────────────┐
               │      Amazon Bedrock       │                     │      Amazon DynamoDB      │
               │   Amazon Nova Pro Model   │                     │      10 Tables (On-Demand)│
               │   (us.amazon.nova-pro-v1) │                     │      • State & Audit Logs │
               └───────────────────────────┘                     └───────────────────────────┘
```

> **Recommended Region**: `us-east-1` (US East, N. Virginia) has full immediate availability for **Amazon Nova Pro**, **Amazon Bedrock AgentCore**, **AWS App Runner**, and **DynamoDB**.

---

## Step 1: Create IAM User & Get AWS Credentials

You need an AWS Access Key ID and Secret Access Key with permissions to interact with Bedrock, DynamoDB, ECR, and App Runner.

### 1.1 Open IAM in the AWS Console
1. Log in to the [AWS Management Console](https://console.aws.amazon.com/).
2. In the top search bar, type **IAM** and select **IAM (Identity and Access Management)**.
3. In the left navigation menu, click **Users**, then click the orange **Create user** button.

### 1.2 Set User Details & Permissions
1. **User name**: Enter `agenthr-deployer`.
2. Leave *"Provide user access to the AWS Management Console"* **unchecked** (this is a programmatic API user). Click **Next**.
3. Under **Permissions options**, select **Attach policies directly**.
4. In the policy search box, search and check the following **4 AWS Managed Policies**:
   - `AmazonBedrockFullAccess` *(allows calling Bedrock models & AgentCore)*
   - `AmazonDynamoDBFullAccess` *(allows creating and querying AgentHR DynamoDB tables)*
   - `AWSAppRunnerFullAccess` *(allows deploying container services on App Runner)*
   - `AmazonEC2ContainerRegistryFullAccess` *(allows pushing Docker images to ECR)*
5. Click **Next**, review the user, and click **Create user**.

### 1.3 Generate Access Keys
1. In the **Users** list, click on your newly created user (`agenthr-deployer`).
2. Go to the **Security credentials** tab.
3. Scroll down to the **Access keys** section and click **Create access key**.
4. Select **Command Line Interface (CLI)** as the use case. Check the confirmation checkbox at the bottom and click **Next**.
5. (Optional) Enter a description tag like `AgentHR deployment key`, then click **Create access key**.
6. **IMPORTANT**: You will see your **Access key ID** and **Secret access key**.
   - Click **Download .csv file** or copy both strings to a secure place.
   - *(You will never be able to see the Secret Access Key again after closing this screen).*
7. Click **Done**.

---

## Step 2: Enable Amazon Nova Model Access in Bedrock

In Amazon Bedrock, foundation models must be explicitly granted access before your account can invoke them. This is free and takes 30 seconds.

1. In the AWS Console top search bar, search for **Amazon Bedrock**.
2. **Make sure your region in the top-right corner is set to `us-east-1` (N. Virginia)**.
3. In the Bedrock left-hand sidebar, scroll down to the bottom and click **Model access**.
4. Click the orange **Enable specific models** (or **Modify model access**) button on the top right.
5. In the model catalog list, scroll to **Amazon**:
   - Check **Amazon Nova Pro** (`amazon.nova-pro-v1:0`) *(Primary reasoning model)*
   - Check **Amazon Nova Lite** (`amazon.nova-lite-v1:0`) *(Fallback lightweight model)*
6. Click **Next**, then review and click **Submit**.
7. The status for Amazon Nova Pro will turn green: **Access granted**.

---

## Step 3: Configure AWS Credentials on Your Machine

### Option A: Using the AWS CLI (Recommended)
If you have the `aws` CLI installed on your machine:
```bash
aws configure
```
Enter your details when prompted:
```text
AWS Access Key ID [None]: YOUR_ACCESS_KEY_ID
AWS Secret Access Key [None]: YOUR_SECRET_ACCESS_KEY
Default region name [None]: us-east-1
Default output format [None]: json
```

### Option B: Using the `.env` File
Alternatively, configure them directly inside `AgentHR/.env`:
```bash
cd AgentHR
cp .env.example .env
```
Edit `.env` with your editor:
```env
# AWS credentials
AWS_ACCESS_KEY_ID=YOUR_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY=YOUR_SECRET_ACCESS_KEY
AWS_REGION=us-east-1

# Amazon Bedrock Settings
BEDROCK_MODEL_ID=us.amazon.nova-pro-v1:0
LLM_BACKEND=bedrock

# Datastore Settings
STORE_BACKEND=dynamodb
DYNAMODB_TABLE_PREFIX=agenthr_

# Human-in-the-Loop approval gate
ENABLE_APPROVAL_GATE=1
AGENT_AUTONOMOUS=1
```

### Verify Credentials
Test that your environment can reach AWS:
```bash
python3 -c "import boto3; sts = boto3.client('sts'); print('Connected as Account:', sts.get_caller_identity()['Account'])"
```
If this prints your 12-digit AWS Account ID, your credentials are fully working!

---

## Step 4: Provision Amazon DynamoDB Tables

AgentHR uses 10 DynamoDB tables to persist applications, jobs, candidate profiles, interview bookings, and audit logs.

Run the automated setup script:
```bash
python scripts/dynamodb_setup.py --region us-east-1 --prefix agenthr_
```

### What this script does:
1. Provisions all 10 tables with **On-Demand (Pay-Per-Request)** billing:
   - `agenthr_jobs`
   - `agenthr_candidates`
   - `agenthr_applications`
   - `agenthr_decisions`
   - `agenthr_interviews`
   - `agenthr_human_reviews`
   - `agenthr_approvals`
   - `agenthr_emails`
   - `agenthr_activity_log`
   - `agenthr_users`
2. Seeds default administrator credentials (`hr@agenthr.ai` / `admin123`) and a sample **Senior Backend Engineer** job description.

> **Cost Note**: On-Demand DynamoDB tables have **no hourly fees** and cost **$0.00** when idle.

---

## Step 5: Deploy to AWS App Runner (Live Public URL)

**AWS App Runner** is the fastest and cleanest way to run AgentHR on AWS with an automatic public HTTPS URL and zero infrastructure management.

### 5.1 Run the Automated Deployment Script
Make sure Docker is running on your machine, then execute:
```bash
cd AgentHR
export AWS_REGION=us-east-1
bash scripts/deploy_apprunner.sh
```

### 5.2 What the Deployment Script Does Automatically:
1. **Creates an ECR Repository**: Provisions `agenthr` in Amazon Elastic Container Registry.
2. **Authenticates Docker**: Logs your local Docker daemon into your private AWS ECR.
3. **Builds & Pushes the Image**: Builds the container via `Dockerfile` and pushes tag `:latest` to ECR.
4. **Provisions App Runner Service**: Creates the service named `agenthr` pointing to the ECR image on container port `8080`, with 1 vCPU and 2 GB RAM.

### 5.3 Monitor Deployment & Get Your Live URL
1. Go to the [AWS App Runner Console](https://console.aws.amazon.com/apprunner/home?region=us-east-1).
2. Click on the `agenthr` service.
3. Under **Status**, you will see: `Operation in progress` (building/deploying ~3-4 minutes).
4. Once the status shows **Running** in green, locate your **Default domain** URL:
   ```
   https://xxxxxxxx.us-east-1.awsapprunner.com
   ```
5. Click the link to view your live, production **AgentHR application**!

---

## Step 6: Deploy to Amazon Bedrock AgentCore Runtime

AgentHR natively conforms to the **Amazon Bedrock AgentCore Runtime** specification with standard `POST /invocations` and `GET /ping` endpoints.

### 6.1 Create the AgentCore IAM Role
In IAM, create a role for Bedrock AgentCore execution:
- **Trusted entity**: Bedrock (`bedrock.amazonaws.com`)
- **Attached Policies**: `AmazonBedrockFullAccess`, `AmazonDynamoDBFullAccess`
- Copy the Role ARN: `arn:aws:iam::<ACCOUNT_ID>:role/AgentHRAgentCoreRole`

### 6.2 Execute the AgentCore Deployment Script
```bash
python scripts/deploy_agentcore.py \
  --image-uri <YOUR_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/agenthr:latest \
  --role-arn arn:aws:iam::<YOUR_ACCOUNT_ID>:role/AgentHRAgentCoreRole \
  --region us-east-1 \
  --runtime-name agenthr-runtime
```

### 6.3 Test AgentCore Endpoints Locally or Remotely
```bash
python scripts/test_agentcore_endpoints.py
```
This tests:
- `GET /ping` → Verifies container health
- `POST /invocations` → Dispatches recruitment actions to the Strands coordinator agent

---

## Step 7: Verify the Live Deployment

### 7.1 Test Candidate Submission
1. Open your live App Runner URL in your browser.
2. In the **Careers (Candidate)** portal, select the Senior Backend Engineer job.
3. Upload a sample resume (e.g. `sample_cvs/strong_candidate.pdf` or paste text from `sample_cvs/strong_candidate.txt`).
4. Submit the application.

### 7.2 Test the Supervised Human Checkpoint (HITL)
1. Switch to the **Recruiter Admin Portal** at the top right.
2. Log in with:
   - **Email**: `hr@agenthr.ai`
   - **Password**: `admin123`
3. Navigate to the **Action Approvals** tab.
4. You will see the pending action for Sarah Ali (`schedule_interview` & `draft_candidate_email`).
5. Review the proposed interview slot and personalized email body generated by Amazon Nova Pro.
6. Click **Approve Action**.
7. Check the **Calendar** tab — the interview is booked!
8. Check the **Activity Log** tab — review the auditable decision chain.

---

## Step 8: Cost Optimization & Teardown (Keep Costs $0)

When you are done testing or judging is complete, tear down or pause resources to ensure you are not billed:

### 1. Pause or Delete the App Runner Service
In the AWS Console:
- Go to **App Runner** -> `agenthr` -> **Actions** -> **Pause service** (no compute charges while paused) or **Delete service**.

Or via AWS CLI:
```bash
SERVICE_ARN=$(aws apprunner list-services --region us-east-1 --query "ServiceSummaryList[?ServiceName=='agenthr'].ServiceArn" --output text)
aws apprunner delete-service --service-arn "$SERVICE_ARN" --region us-east-1
```

### 2. Delete ECR Repository Images
```bash
aws ecr delete-repository --repository-name agenthr --force --region us-east-1
```

### 3. DynamoDB Tables
Since the tables were created with **PAY_PER_REQUEST (On-Demand)**, they cost **$0.00/month** when not receiving requests. If you prefer to delete them completely:
```bash
for tbl in jobs candidates applications decisions interviews human_reviews approvals emails activity_log users; do
  aws dynamodb delete-table --table-name "agenthr_${tbl}" --region us-east-1
done
```

---

## Troubleshooting & FAQs

### Q: "ResourceNotFoundException" or "AccessDeniedException" when calling Bedrock
**Fix**: Ensure you performed **Step 2** (Model access request in the Amazon Bedrock Console) in the `us-east-1` region. Bedrock models cannot be invoked until access is granted in the console.

### Q: "Cannot connect to Docker daemon" during deployment
**Fix**: Ensure Docker Desktop / Docker Engine is running on your local machine before running `bash scripts/deploy_apprunner.sh`.

### Q: Can I run the app locally while connected to real AWS Bedrock & DynamoDB?
**Yes!** Set `STORE_BACKEND=dynamodb` and `LLM_BACKEND=bedrock` in your `.env` file, ensure your AWS credentials are set, and run:
```bash
python3 -m app.main &
streamlit run frontend/streamlit_app.py
```
This runs the frontend and backend locally on your computer while executing all AI reasoning against Amazon Bedrock and persisting all data in Amazon DynamoDB.

