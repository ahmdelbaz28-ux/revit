# FireAlarmAI AWS Infrastructure

Production-ready AWS infrastructure as code using Terraform.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     AWS Cloud                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                  VPC (10.0.0.0/16)                   │  │
│  │  ┌───────────────────────────────────────────────┐   │  │
│  │  │ Public Subnets (x3)                          │   │  │
│  │  │ - NAT Gateway x3                              │   │  │
│  │  │ - ALB (HTTPS)                                │   │  │
│  │  └───────────────────────────────────────────────┘   │  │
│  │  ┌───────────────────────────────────────────────┐   │  │
│  │  │ Private Subnets (x3)                        │   │  │
│  │  │ - ECS Fargate Containers                    │   │  │
│  │  └───────────────────────────────────────────────┘   │  │
│  │  ┌───────────────────────────────────────────────┐   │  │
│  │  │ Database Subnets (x3)                       │   │  │
│  │  │ - RDS PostgreSQL 15                        │   │  │
│  │  └───────────────────────────────────────────────┘   │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Prerequisites

- AWS CLI configured with credentials
- Terraform >= 1.5.0
- GitHub token for Flux CD

## Quick Start

### 1. Configure AWS credentials

```bash
aws configure
# Or set environment variables
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
```

### 2. Initialize Terraform

```bash
cd infrastructure/terraform
terraform init
```

### 3. Plan the deployment

```bash
terraform plan \
  -var="postgres_master_password=YOUR_SECURE_PASSWORD" \
  -var="acm_certificate_arn=arn:aws:acm:eu-west-2:123456789012:certificate/abc123"
```

### 4. Apply the infrastructure

```bash
terraform apply \
  -var="postgres_master_password=YOUR_SECURE_PASSWORD" \
  -var="acm_certificate_arn=arn:aws:acm:eu-west-2:123456789012:certificate/abc123"
```

## Configuration Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `aws_region` | AWS region | `eu-west-2` |
| `environment_name` | Environment | `production` |
| `project_name` | Project name | `firealarmai` |
| `container_desired_count` | Container instances | `2` |
| `container_max_scaling_count` | Max scaling | `6` |
| `postgres_instance_class` | DB instance class | `db.t4g.medium` |
| `postgres_allocated_storage` | DB storage (GB) | `100` |

## Cost Estimation

| Resource | Monthly Cost (estimate) |
|----------|----------------------|
| RDS PostgreSQL (db.t4g.medium) | $80-120 |
| ECS Fargate (2 vCPU, 4GB) | $80-150 |
| Application Load Balancer | $25 |
| NAT Gateway (3x) | $50-80 |
| S3, CloudWatch, etc. | $20 |
| **Total** | **$150-300/month** |

## Outputs

After deployment, you will get:

- `vpc_id` - VPC ID
- `database_endpoint` - RDS endpoint (use this to connect)
- `load_balancer_dns_name` - ALB DNS
- `ecr_repository_url` - ECR repository URL

## Cleaning Up

```bash
terraform destroy
```

## Security

- RDS is Multi-AZ with deletion protection
- All storage is encrypted with KMS
- Private subnets with NAT for outbound
- Security groups restrict access
- Secrets stored in Secrets Manager

## License

MIT License