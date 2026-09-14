"""Create an IAM Instance Role for AgentHR on AWS App Runner.

The role grants the running container permission to call:
  - Amazon DynamoDB (read/write all agenthr_ tables)
  - Amazon Bedrock  (invoke Nova Pro foundation model)

Usage:
    python scripts/create_apprunner_role.py [--region us-east-1]

Outputs the Role ARN, which deploy_apprunner.sh reads automatically.
"""
from __future__ import annotations

import argparse
import json
import sys
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

ROLE_NAME = "AgentHRAppRunnerRole"

TRUST_POLICY = json.dumps({
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {"Service": "tasks.apprunner.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }
    ],
})

MANAGED_POLICIES = [
    "arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess",
    "arn:aws:iam::aws:policy/AmazonBedrockFullAccess",
]


def create_role(region: str = "us-east-1") -> str:
    """Create (or fetch existing) IAM role and return its ARN."""
    iam = boto3.client("iam", region_name=region)

    # Create role (idempotent — skip if already exists)
    try:
        print(f"Creating IAM role: {ROLE_NAME} ...", end=" ")
        resp = iam.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=TRUST_POLICY,
            Description="Grants AgentHR App Runner container access to DynamoDB and Bedrock.",
        )
        role_arn = resp["Role"]["Arn"]
        print("CREATED")
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "EntityAlreadyExists":
            role_arn = iam.get_role(RoleName=ROLE_NAME)["Role"]["Arn"]
            print("ALREADY EXISTS")
        else:
            raise

    # Attach managed policies (idempotent)
    for policy_arn in MANAGED_POLICIES:
        policy_name = policy_arn.split("/")[-1]
        try:
            iam.attach_role_policy(RoleName=ROLE_NAME, PolicyArn=policy_arn)
            print(f"  Attached: {policy_name}")
        except ClientError as exc:
            if "already attached" in str(exc).lower():
                print(f"  Already attached: {policy_name}")
            else:
                raise

    print(f"\n✅ IAM Instance Role ARN:\n   {role_arn}")
    return role_arn


def main() -> None:
    parser = argparse.ArgumentParser(description="Create AgentHR App Runner IAM role")
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()
    create_role(args.region)


if __name__ == "__main__":
    main()
