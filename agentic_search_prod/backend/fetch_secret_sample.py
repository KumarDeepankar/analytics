"""
Sample script to fetch Claude LLM OAuth credentials from AWS Secrets Manager.

Prerequisites:
  - pip install boto3
  - AWS credentials configured via one of:
      * ECS task role (automatic on ECS)
      * IAM role / instance profile (on EC2)
      * ~/.aws/credentials or AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY env vars (local dev)

Usage:
  python fetch_secret_sample.py
"""
import json
import boto3
from botocore.exceptions import ClientError


def get_secret(
    secret_name: str = "agentic-search/anthropic",
    region_name: str = "us-east-1"
) -> dict:
    """
    Fetch a secret from AWS Secrets Manager.

    Args:
        secret_name: Name or ARN of the secret
        region_name: AWS region

    Returns:
        dict with keys: client_id, client_secret, pingfederate_url
    """
    client = boto3.client("secretsmanager", region_name=region_name)

    try:
        response = client.get_secret_value(SecretId=secret_name)
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "ResourceNotFoundException":
            print(f"Secret '{secret_name}' not found in region '{region_name}'")
        elif error_code == "AccessDeniedException":
            print(f"Access denied. Check IAM policy for secretsmanager:GetSecretValue")
        elif error_code == "InvalidRequestException":
            print(f"Invalid request: secret may be pending deletion")
        else:
            print(f"AWS error ({error_code}): {e}")
        raise

    secret_dict = json.loads(response["SecretString"])
    return secret_dict


if __name__ == "__main__":
    secret = get_secret()

    client_id = secret["client_id"]
    client_secret = secret["client_secret"]
    pingfederate_url = secret["pingfederate_url"]

    print(f"client_id:        {client_id}")
    print(f"client_secret:    {client_secret[:8]}********")  # mask for safety
    print(f"pingfederate_url: {pingfederate_url}")
