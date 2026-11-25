import os

import boto3

NAMESPACE = os.getenv("METRICS_NAMESPACE", "Lab10/ItemsApp")
SERVICE = os.getenv("SERVICE_NAME", "items-api")
DIMS = [{"Name": "Service", "Value": SERVICE}]


def cloudwatch():
    return boto3.client(
        "cloudwatch",
        endpoint_url=os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566"),
        region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "test"),
    )
