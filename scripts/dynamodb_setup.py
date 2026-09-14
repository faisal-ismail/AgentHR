"""Provision DynamoDB tables for AgentHR in the target AWS account/region.

Creates 10 tables with partition key 'id' (String) and PAY_PER_REQUEST billing:
  - {prefix}jobs
  - {prefix}candidates
  - {prefix}applications
  - {prefix}decisions
  - {prefix}interviews
  - {prefix}human_reviews
  - {prefix}approvals
  - {prefix}emails
  - {prefix}activity_log
  - {prefix}users

Usage:
  python scripts/dynamodb_setup.py [--region us-east-1] [--prefix agenthr_]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Ensure AgentHR root is in sys.path and .env is loaded
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

try:
    from dotenv import load_dotenv
    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
except ImportError:
    pass

import boto3
from botocore.exceptions import ClientError

TABLE_NAMES = [
    "jobs",
    "candidates",
    "applications",
    "decisions",
    "interviews",
    "human_reviews",
    "approvals",
    "emails",
    "activity_log",
    "users",
]


def setup_tables(region: str = "us-east-1", prefix: str = "agenthr_") -> None:
    print(f"Setting up DynamoDB tables in region: {region} with prefix: '{prefix}'...")
    dynamodb = boto3.client("dynamodb", region_name=region)

    for name in TABLE_NAMES:
        full_table_name = f"{prefix}{name}"
        try:
            print(f"Checking table: {full_table_name} ...", end=" ")
            dynamodb.describe_table(TableName=full_table_name)
            print("EXISTS")
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ResourceNotFoundException":
                print("CREATING ...", end=" ")
                dynamodb.create_table(
                    TableName=full_table_name,
                    KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
                    AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
                    BillingMode="PAY_PER_REQUEST",
                )
                print("CREATED (provisioning)")
            else:
                print(f"ERROR: {exc}")
                raise

    print("\nAll DynamoDB tables initialized successfully!")


def main() -> None:
    parser = argparse.ArgumentParser(description="Provision AgentHR DynamoDB tables")
    parser.add_argument("--region", default="us-east-1", help="AWS region (default: us-east-1)")
    parser.add_argument("--prefix", default="agenthr_", help="Table prefix (default: agenthr_)")
    args = parser.parse_args()
    setup_tables(region=args.region, prefix=args.prefix)


if __name__ == "__main__":
    main()

