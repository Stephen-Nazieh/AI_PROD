GCP to AWS Service Mapping (for migrations)

Compute: Compute Engine = EC2; Cloud Run = App Runner/Fargate; Cloud Functions =
Lambda; GKE = EKS.
Storage: Cloud Storage = S3; Persistent Disk = EBS; Filestore = EFS.
Database: Cloud SQL = RDS; Spanner = Aurora (globally); Firestore = DynamoDB;
BigQuery = Redshift/Athena.
Networking: Cloud Load Balancing = ELB/ALB; Cloud CDN = CloudFront; Cloud DNS =
Route 53; VPC = VPC.
Identity: Cloud IAM = IAM; Workload Identity = IAM Roles for Service Accounts.
Messaging: Pub/Sub = SNS+SQS; Cloud Tasks = SQS.
Ops: Cloud Logging/Monitoring = CloudWatch; Cloud Build = CodeBuild/CodePipeline.

Migration tip: identity and networking models differ most — map IAM bindings and
VPC/peering early; data egress costs dominate large migrations.
