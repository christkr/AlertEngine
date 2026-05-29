from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_iam as iam,
)
from constructs import Construct

from alert_engine.storage_stack import StorageStack

class ComputeStack(Stack):
    """
    Stateless compute resources, safe to destroy
    Needs StorageStack for table/bucket/repo references
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        storage_stack: StorageStack,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        """
        VPC, 2 AZs and 1 public subnet per AZ
        Fargate tasks will run in public subnets to reach Cheapshark without NAT Gateway (minimize cost for v1)
        """
        self.vpc = ec2.Vpc(
            self,
            "AlertEngineVpc",
            max_azs=2,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                )
            ],
            nat_gateways=0,
        )

        """
        ECS cluster
        No EC2 capacity, sticking to Fargate
        Container Insights off (minimize cost for v1)
        """
        self.ecs_cluster = ecs.Cluster(
            self,
            "AlertEngineCluster",
            cluster_name="alert-engine",
            vpc=self.vpc,
            container_insights=False,
        )

        """
        IAM Fargate task execution role
        Used by ECS control plane to pull container image from ECR and send container logs to Cloudwatch
        """
        self.task_execution_role = iam.Role(
            self,
            "FetcherTaskExecutionRole",
            role_name="alert-engine-fetcher-execution",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                )
            ],
            description="ECS control plane role: ECR pull + CloudWatch log sending",
        )

        """
        IAM Fargate task role
        Used by application code
        Permissions granted:
            s3:PutObject scoped to the raw archive bucket
            dynamodb:PutItem scoped to the price history table
        note: no s3 getobject or dynamod query, write only for now; future versions could have read perms if needed
        """
        self.task_role = iam.Role(
            self,
            "FetcherTaskRole",
            role_name="alert-engine-fetcher-task",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            description="Application role for the fetcher container",
        )

        storage_stack.raw_archive_bucket.grant_put(self.task_role)
        storage_stack.price_history_table.grant_write_data(self.task_role)
