import os

import aws_cdk as cdk

from alert_engine.storage_stack import StorageStack
from alert_engine.compute_stack import ComputeStack

app = cdk.App()

env = cdk.Environment(account=os.getenv("AWS_ACCOUNT_ID"), region=os.getenv("AWS_REGION"))

storage = StorageStack(
    app,
    "AlertEngineStorage",
    env=env,
    description="AlertEngine persistent storage: DynamoDB, S3, ECR, OIDC",
)

compute = ComputeStack(
    app,
    "AlertEngineCompute",
    storage_stack=storage,
    env=env,
    description="AlertEngine stateless compute: VPC, ECS Fargate cluster, IAM",
)

app.synth()