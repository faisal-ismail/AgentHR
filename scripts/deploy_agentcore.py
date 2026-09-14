"""Deploy AgentHR to Amazon Bedrock AgentCore Runtime using boto3.

Usage:
  python scripts/deploy_agentcore.py --image-uri <ECR_IMAGE_URI> --role-arn <ROLE_ARN> [--region us-east-1]
"""
from __future__ import annotations

import argparse
import sys
import boto3


def deploy(image_uri: str, role_arn: str, region: str = "us-east-1", runtime_name: str = "agenthr-runtime") -> None:
    print(f"Deploying AgentHR to Amazon Bedrock AgentCore Runtime...")
    print(f"  Region:       {region}")
    print(f"  Runtime Name: {runtime_name}")
    print(f"  Container:    {image_uri}")
    print(f"  Role ARN:     {role_arn}")

    try:
        client = boto3.client("bedrock-agentcore-control", region_name=region)
        response = client.create_agent_runtime(
            agentRuntimeName=runtime_name,
            agentRuntimeArtifact={
                "containerConfiguration": {
                    "containerUri": image_uri
                }
            },
            networkConfiguration={"networkMode": "PUBLIC"},
            roleArn=role_arn,
        )
        runtime_arn = response.get("agentRuntimeArn", "N/A")
        print(f"SUCCESS: AgentHR deployed to Bedrock AgentCore Runtime!")
        print(f"  Agent Runtime ARN: {runtime_arn}")
    except Exception as exc:
        print(f"ERROR: Deployment failed: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy AgentHR to Amazon Bedrock AgentCore Runtime")
    parser.add_argument("--image-uri", required=True, help="Amazon ECR container image URI")
    parser.add_argument("--role-arn", required=True, help="IAM Role ARN for AgentCore Runtime")
    parser.add_argument("--region", default="us-east-1", help="AWS Region (default: us-east-1)")
    parser.add_argument("--runtime-name", default="agenthr-runtime", help="AgentCore runtime name")

    args = parser.parse_args()
    deploy(args.image_uri, args.role_arn, args.region, args.runtime_name)


if __name__ == "__main__":
    main()

