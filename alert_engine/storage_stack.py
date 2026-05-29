import os
from aws_cdk import (
    Stack,
    RemovalPolicy,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
    aws_ecr as ecr,
    aws_iam as iam,
)
from constructs import Construct


class StorageStack(Stack):
    """
    Persistent resources that should survive compute teardowns.
    Exports table/bucket/repo references for ComputeStack to consume.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        """
        DynamoDB rules table
        Partition Key : rule_id
        """
        self.rules_table = dynamodb.Table(
            self,
            "RulesTable",
            table_name="alert-engine-rules",
            partition_key=dynamodb.Attribute(
                name="rule_id",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
            point_in_time_recovery=True,
        )

        """
        DynamoDB price history table
        Partition Key : source#entity_id
        Sort Key : ISO timestamp
        """
        self.price_history_table = dynamodb.Table(
            self,
            "PriceHistoryTable",
            table_name="alert-engine-price-history",
            partition_key=dynamodb.Attribute(
                name="source_entity",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
            point_in_time_recovery=True,
        )

        """
        S3 raw api response archive
        """
        self.raw_archive_bucket = s3.Bucket(
            self,
            "RawArchiveBucket",
            removal_policy=RemovalPolicy.RETAIN,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            versioned=False,
            enforce_ssl=True,
        )

        """
        ECR Cheapshark fetcher image repo
        """
        self.fetcher_repo = ecr.Repository(
            self,
            "FetcherRepo",
            repository_name="alert-engine-fetcher",
            removal_policy=RemovalPolicy.DESTROY,
            empty_on_delete=True,
        )

        """
        IAM GH Actions OIDC
        Permissions given :
            ecr:GetAuthorizationToken
            ecr:BatchCheckLayerAvailability, ecr:PutImage, ...
            sts:AssumeRole for CDK deploy
        """
        github_oidc_provider = iam.OpenIdConnectProvider(
            self,
            "GitHubOidcProvider",
            url="https://token.actions.githubusercontent.com",
            client_ids=["sts.amazonaws.com"],
        )

        github_org = os.environ.get("GITHUB_ORG", "christkr")
        github_repo = os.environ.get("GITHUB_REPO", "AlertEngine")

        self.github_actions_role = iam.Role(
            self,
            "GitHubActionsRole",
            role_name="alert-engine-github-actions",
            assumed_by=iam.WebIdentityPrincipal(
                github_oidc_provider.open_id_connect_provider_arn,
                conditions={
                    "StringLike": {
                        "token.actions.githubusercontent.com:sub": (
                            f"repo:{github_org}/{github_repo}:*"
                        )
                    },
                    "StringEquals": {
                        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
                    },
                },
            ),
            description="Assumed by GitHub Actions via OIDC for CDK deploy and ECR push",
        )

        """
        ECR push permissions scoped to fetcher repo only
        """
        self.github_actions_role.add_to_policy(
            iam.PolicyStatement(
                sid="ECRAuthToken",
                actions=["ecr:GetAuthorizationToken"],
                resources=["*"],
            )
        )

        self.github_actions_role.add_to_policy(
            iam.PolicyStatement(
                sid="ECRPush",
                actions=[
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:CompleteLayerUpload",
                    "ecr:InitiateLayerUpload",
                    "ecr:PutImage",
                    "ecr:UploadLayerPart",
                    "ecr:BatchGetImage",
                    "ecr:GetDownloadUrlForLayer",
                ],
                resources=[self.fetcher_repo.repository_arn],
            )
        )

        self.github_actions_role.add_to_policy(
            iam.PolicyStatement(
                sid="CDKDeploy",
                actions=["sts:AssumeRole"],
                resources=[f"arn:aws:iam::{self.account}:role/cdk-*"],
            )
        )