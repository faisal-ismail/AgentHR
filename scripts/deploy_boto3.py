"""AgentHR — Full AWS Deployment via boto3 (No Docker, No AWS CLI required).

Deploys AgentHR to AWS App Runner using the ECR image OR falls back to
creating an App Runner service that builds from a GitHub-connected repo.

Since App Runner source-based deployments only support GitHub/Bitbucket,
this script uses a different no-Docker strategy:

  Strategy: AWS Elastic Beanstalk (Python platform)
  - Zips source code
  - Uploads to S3
  - Creates / updates an Elastic Beanstalk Python 3.12 environment
  - Elastic Beanstalk runs entrypoint.sh via Procfile

Usage:
    python3 scripts/deploy_boto3.py [--region us-east-1]

Requirements:
    pip3 install boto3 --break-system-packages   (already done)
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
import zipfile
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=project_root / ".env")
except ImportError:
    pass

import boto3
from botocore.exceptions import ClientError

# ── Config ───────────────────────────────────────────────────────────────────
APP_NAME    = "agenthr"
ENV_NAME    = "agenthr-prod"
BUCKET_NAME_TMPL = "agenthr-deploy-{account}"
ZIP_KEY     = "agenthr-source.zip"
ROLE_NAME   = "AgentHRAppRunnerRole"   # reused for EB instance profile

EXCLUDE_DIRS = {
    ".git", ".venv", ".venv_aws", "venv", "env", "aws_env",
    "__pycache__", "website", "sample_cvs",
}
EXCLUDE_FILES = {
    ".env", ".DS_Store", "agenthr-deployer_accessKeys.csv",
}
EXCLUDE_EXTS = {".pyc", ".pyo", ".log"}

# AWS credentials injected as env vars
AWS_ACCESS_KEY_ID  = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_KEY     = os.getenv("AWS_SECRET_ACCESS_KEY", "")

ENV_VARS = {
    "STORE_BACKEND":        "dynamodb",
    "DYNAMODB_TABLE_PREFIX":"agenthr_",
    "LLM_BACKEND":          "bedrock",
    "BEDROCK_MODEL_ID":     "us.amazon.nova-pro-v1:0",
    "AGENT_AUTONOMOUS":     "1",
    "ENABLE_APPROVAL_GATE": "1",
    "APP_HOST":             "0.0.0.0",
    "APP_PORT":             "8000",
    "ADMIN_EMAIL":          "hr@agenthr.ai",
    "ADMIN_PASSWORD":       "admin123",
    "SECRET_KEY":           "agenthr-prod-secret-change-me",
    "AWS_ACCESS_KEY_ID":    AWS_ACCESS_KEY_ID,
    "AWS_SECRET_ACCESS_KEY": AWS_SECRET_KEY,
}


def banner(msg: str) -> None:  # noqa: D401
    print(f"\n{'─'*56}")
    print(f"  {msg}")
    print(f"{'─'*56}")


# ── Step 1: IAM setup ─────────────────────────────────────────────────────────
def setup_iam(region: str, account_id: str) -> tuple[str, str]:
    """Create instance role + instance profile for Elastic Beanstalk."""
    iam = boto3.client("iam", region_name=region)

    trust = json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "ec2.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }]
    })

    try:
        role_arn = iam.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=trust,
            Description="AgentHR EB instance role",
        )["Role"]["Arn"]
        print(f"  Created IAM role: {ROLE_NAME}")
    except ClientError as e:
        if e.response["Error"]["Code"] == "EntityAlreadyExists":
            role_arn = iam.get_role(RoleName=ROLE_NAME)["Role"]["Arn"]
            print(f"  IAM role exists: {ROLE_NAME}")
        else:
            raise

    for policy in [
        "arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess",
        "arn:aws:iam::aws:policy/AmazonBedrockFullAccess",
        "arn:aws:iam::aws:policy/AWSElasticBeanstalkWebTier",
    ]:
        try:
            iam.attach_role_policy(RoleName=ROLE_NAME, PolicyArn=policy)
        except ClientError:
            pass  

    profile_name = f"{ROLE_NAME}-profile"
    try:
        iam.create_instance_profile(InstanceProfileName=profile_name)
        iam.add_role_to_instance_profile(InstanceProfileName=profile_name, RoleName=ROLE_NAME)
        print(f"  Created instance profile: {profile_name}")
        import time
        print("  Waiting 10s for IAM profile to propagate...")
        time.sleep(10)
    except ClientError as e:
        if e.response["Error"]["Code"] == "EntityAlreadyExists":
            print(f"  Instance profile exists: {profile_name}")
        else:
            raise

    return role_arn, profile_name


# ── Step 2: S3 bucket ─────────────────────────────────────────────────────────
def ensure_bucket(s3, region: str, bucket: str) -> None:
    try:
        s3.head_bucket(Bucket=bucket)
        print(f"  S3 bucket exists: {bucket}")
    except ClientError:
        kwargs: dict = {"Bucket": bucket}
        if region != "us-east-1":
            kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
        s3.create_bucket(**kwargs)
        print(f"  Created S3 bucket: {bucket}")


# ── Step 3: Zip source ────────────────────────────────────────────────────────
def build_zip(root: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if path.is_dir():
                continue
            rel = path.relative_to(root)
            parts = rel.parts
            if any(p in EXCLUDE_DIRS for p in parts):
                continue
            if rel.name in EXCLUDE_FILES or rel.suffix in EXCLUDE_EXTS:
                continue
            zf.write(path, str(rel))
            print(f"    + {rel}")
    return buf.getvalue()


# ── Step 4: Elastic Beanstalk deploy ─────────────────────────────────────────
def deploy_eb(region: str, bucket: str, profile_name: str, zip_data: bytes) -> str:
    eb = boto3.client("elasticbeanstalk", region_name=region)
    s3 = boto3.client("s3", region_name=region)

    # Upload source bundle
    version_label = f"agenthr-{int(time.time())}"
    s3.put_object(Bucket=bucket, Key=ZIP_KEY, Body=zip_data)
    print(f"  Uploaded source bundle → s3://{bucket}/{ZIP_KEY}")

    # Create application (idempotent)
    try:
        eb.create_application(ApplicationName=APP_NAME, Description="AgentHR recruitment agent")
        print(f"  Created EB application: {APP_NAME}")
    except ClientError as e:
        if "already exists" in str(e):
            print(f"  EB application exists: {APP_NAME}")
        else:
            raise

    # Create application version
    eb.create_application_version(
        ApplicationName=APP_NAME,
        VersionLabel=version_label,
        SourceBundle={"S3Bucket": bucket, "S3Key": ZIP_KEY},
        AutoCreateApplication=False,
    )
    print(f"  Created version: {version_label}")

    # Build option settings
    option_settings = [
        {"Namespace": "aws:autoscaling:launchconfiguration",
         "OptionName": "IamInstanceProfile", "Value": profile_name},
        {"Namespace": "aws:elasticbeanstalk:environment",
         "OptionName": "EnvironmentType", "Value": "SingleInstance"},
        {"Namespace": "aws:ec2:instances",
         "OptionName": "InstanceTypes", "Value": "t3.small"},
    ]
    for name, value in ENV_VARS.items():
        option_settings.append({
            "Namespace": "aws:elasticbeanstalk:application:environment",
            "OptionName": name,
            "Value": value,
        })
    # Add AWS region for boto3 inside the container
    option_settings.append({
        "Namespace": "aws:elasticbeanstalk:application:environment",
        "OptionName": "AWS_DEFAULT_REGION",
        "Value": region,
    })

    # Check if env exists → update or create
    envs = eb.describe_environments(
        ApplicationName=APP_NAME, EnvironmentNames=[ENV_NAME], IncludeDeleted=False
    )["Environments"]

    if envs and envs[0]["Status"] not in ("Terminated", "Terminating"):
        print(f"  Updating existing EB environment: {ENV_NAME} (clearing WSGIPath)")
        eb.update_environment(
            ApplicationName=APP_NAME,
            EnvironmentName=ENV_NAME,
            VersionLabel=version_label,
            OptionSettings=option_settings,
            OptionsToRemove=[
                {
                    "Namespace": "aws:elasticbeanstalk:container:python",
                    "OptionName": "WSGIPath"
                }
            ]
        )
    else:
        print(f"  Creating new EB environment: {ENV_NAME}")
        stacks = eb.list_available_solution_stacks().get("SolutionStacks", [])
        py_stacks = [s for s in stacks if "Python 3.12" in s]
        if not py_stacks:
            py_stacks = [s for s in stacks if "Python 3.11" in s]
        solution_stack = sorted(py_stacks)[-1] if py_stacks else ""
        if not solution_stack:
            raise RuntimeError("No Python 3.12/3.11 EB stack found. Run: aws elasticbeanstalk list-available-solution-stacks")
        print(f"  Using solution stack: {solution_stack}")
        eb.create_environment(
            ApplicationName=APP_NAME,
            EnvironmentName=ENV_NAME,
            VersionLabel=version_label,
            SolutionStackName=solution_stack,
            OptionSettings=option_settings,
        )

    # Poll until ready
    print("\n  ⏳ Waiting for deployment to complete (this takes ~5-8 minutes)...")
    for i in range(40):
        time.sleep(15)
        env = eb.describe_environments(
            ApplicationName=APP_NAME, EnvironmentNames=[ENV_NAME]
        )["Environments"][0]
        status = env.get("Status", "Unknown")
        health = env.get("HealthStatus", "")
        cname  = env.get("CNAME", "")
        print(f"  [{i+1}/40] Status: {status} | Health: {health} {('| URL: http://' + cname) if cname else ''}")
        if status == "Ready":
            return f"http://{cname}"
        if status in ("Terminated", "Failed"):
            raise RuntimeError(f"Deployment failed with status: {status}")

    return ""


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy AgentHR to AWS (no Docker needed)")
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"))
    args = parser.parse_args()
    region = args.region

    sts = boto3.client("sts", region_name=region,
                       aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                       aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"))
    account_id = sts.get_caller_identity()["Account"]
    bucket = BUCKET_NAME_TMPL.format(account=account_id)

    print(f"\n{'═'*56}")
    print("  AgentHR — AWS Deployment (No Docker / No CLI)")
    print(f"{'═'*56}")
    print(f"  Account : {account_id}")
    print(f"  Region  : {region}")
    print(f"  Method  : Elastic Beanstalk Python 3.12")

    print(f"  AWS creds loaded: {'✅' if AWS_ACCESS_KEY_ID else '❌ MISSING'}")

    banner("Step 1/4 — IAM Instance Role")
    _, profile_name = setup_iam(region, account_id)

    banner("Step 2/4 — S3 Bucket")
    s3 = boto3.client("s3", region_name=region,
                      aws_access_key_id=AWS_ACCESS_KEY_ID,
                      aws_secret_access_key=AWS_SECRET_KEY)
    ensure_bucket(s3, region, bucket)

    banner("Step 3/4 — Building Source Bundle")
    print(f"  Zipping {project_root} ...")
    zip_data = build_zip(project_root)
    print(f"  Bundle size: {len(zip_data) / 1024:.1f} KB")

    banner("Step 4/4 — Elastic Beanstalk Deploy")
    url = deploy_eb(region, bucket, profile_name, zip_data)

    print(f"\n{'═'*56}")
    if url:
        print("  🚀 AgentHR is LIVE!")
        print(f"  URL         : {url}")
        print(f"  Recruiter   : hr@agenthr.ai / admin123")
    else:
        print("  ⏳ Still deploying — check EB console:")
        print(f"  https://console.aws.amazon.com/elasticbeanstalk/home?region={region}")
    print(f"{'═'*56}\n")


if __name__ == "__main__":
    main()
