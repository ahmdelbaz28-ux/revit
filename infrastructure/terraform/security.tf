# =============================================================================
# Security Hardening for FireAlarmAI
# Defense-in-Depth: WAF, Shield, GuardDuty, Security Hub, CloudTrail, KMS, Secrets
# =============================================================================

# =============================================================================
# KMS Keys
# =============================================================================

resource "aws_kms_key" "application_encryption_key" {
  description             = "Encrypts application secrets and sensitive data"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Enable IAM User Permissions"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${var.aws_account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "Allow Secrets Manager"
        Effect = "Allow"
        Principal = {
          Service = "secretsmanager.amazonaws.com"
        }
        Action = [
          "kms:GenerateDataKey",
          "kms:Decrypt"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "kms:CallerAccount" = var.aws_account_id
          }
        }
      },
      {
        Sid    = "Allow CloudWatch Logs"
        Effect = "Allow"
        Principal = {
          Service = "logs.${var.aws_region}.amazonaws.com"
        }
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:DescribeKey"
        ]
        Resource = "*"
        Condition = {
          ArnLike = {
            "kms:EncryptionContext:aws:logs:arn" = "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:*"
          }
        }
      }
    ]
  })

  tags = {
    Name        = "${var.project_name}-${var.environment_name}-application-key"
    Environment = var.environment_name
    Project     = var.project_name
  }
}

resource "aws_kms_alias" "application_encryption_key_alias" {
  name          = "alias/${var.project_name}-${var.environment_name}-app-key"
  target_key_id = aws_kms_key.application_encryption_key.key_id
}

# =============================================================================
# Secrets Manager
# =============================================================================

resource "aws_secretsmanager_secret" "database_secret" {
  name                    = "${var.project_name}/${var.environment_name}/database"
  description             = "RDS PostgreSQL database credentials"
  kms_key_id              = aws_kms_key.application_encryption_key.id
  recovery_window_in_days = 7

  tags = {
    Name        = "${var.project_name}-${var.environment_name}-db-secret"
    Environment = var.environment_name
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret" "api_key_secret" {
  name                    = "${var.project_name}/${var.environment_name}/api-keys"
  description             = "API signing keys and JWT secrets"
  kms_key_id              = aws_kms_key.application_encryption_key.id
  recovery_window_in_days = 7

  tags = {
    Name        = "${var.project_name}-${var.environment_name}-api-keys-secret"
    Environment = var.environment_name
    Project     = var.project_name
  }
}

# =============================================================================
# IAM Policy - Least Privilege
# =============================================================================

resource "aws_iam_policy" "ecs_task_database_access_policy" {
  name        = "${var.project_name}-${var.environment_name}-ecs-database-access-policy"
  description = "Least privilege policy for ECS tasks to access RDS and secrets"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "AllowRDSDataAPI"
        Effect   = "Allow"
        Action   = [
          "rds-data:ExecuteStatement",
          "rds-data:BatchExecuteStatement",
          "rds-data:BeginTransaction",
          "rds-data:CommitTransaction",
          "rds-data:RollbackTransaction"
        ]
        Resource = "arn:aws:rds:${var.aws_region}:${var.aws_account_id}:cluster:${aws_db_instance.postgres_database.resource_id}"
      },
      {
        Sid      = "AllowRDSConnect"
        Effect   = "Allow"
        Action   = [
          "rds-db:connect"
        ]
        Resource = "arn:aws:rds-db:${var.aws_region}:${var.aws_account_id}:dbuser:${aws_db_instance.postgres_database.resource_id}/${var.postgres_master_username}"
      },
      {
        Sid      = "AllowSecretsManagerRead"
        Effect   = "Allow"
        Action   = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = [
          aws_secretsmanager_secret.database_secret.arn,
          aws_secretsmanager_secret.api_key_secret.arn
        ]
      },
      {
        Sid      = "AllowKMSDecrypt"
        Effect   = "Allow"
        Action   = [
          "kms:Decrypt",
          "kms:GenerateDataKey"
        ]
        Resource = [
          aws_kms_key.application_encryption_key.arn,
          aws_kms_key.database_encryption_key.arn
        ]
        Condition = {
          StringEquals = {
            "kms:ViaService" = "secretsmanager.${var.aws_region}.amazonaws.com"
          }
        }
      },
      {
        Sid      = "AllowS3Access"
        Effect   = "Allow"
        Action   = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.access_logs_bucket.arn,
          "${aws_s3_bucket.access_logs_bucket.arn}/*"
        ]
      },
      {
        Sid      = "AllowLogsExport"
        Effect   = "Allow"
        Action   = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams"
        ]
        Resource = "${aws_cloudwatch_log_group.api_log_group.arn}:*"
      },
      {
        Sid      = "DenyProductionWriteAccess"
        Effect   = "Deny"
        Action   = [
          "rds:DeleteDBInstance",
          "rds:ModifyDBCluster",
          "s3:DeleteBucket",
          "kms:ScheduleKeyDeletion",
          "kms:DisableKey"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:RequestedRegion": var.aws_region
          },
          Bool = {
            "aws:ViaAWSService": "false"
          }
        }
      }
    ]
  })
}

# =============================================================================
# Security Groups - Restrictive
# =============================================================================

resource "aws_security_group" "ecs_container_security_group" {
  name        = "${var.project_name}-${var.environment_name}-ecs-container-security"
  description = "Restrictive security group for ECS containers"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "API traffic from ALB only"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb_security_group.id]
  }

  egress {
    description = "Outbound to PostgreSQL RDS"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr_block]
  }

  egress {
    description = "Outbound HTTPS to AWS services"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${var.project_name}-${var.environment_name}-ecs-container-sg"
    Environment = var.environment_name
    Project     = var.project_name
    SecurityTier = "private"
  }
}

resource "aws_security_group" "rds_security_group" {
  name        = "${var.project_name}-${var.environment_name}-rds-security"
  description = "Restrictive security group for RDS PostgreSQL"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "PostgreSQL from ECS containers only"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_container_security_group.id]
  }

  egress {
    description = "Allow all outbound for patching"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${var.project_name}-${var.environment_name}-rds-sg"
    Environment = var.environment_name
    Project     = var.project_name
    SecurityTier = "database"
  }
}

resource "aws_security_group" "alb_security_group" {
  name        = "${var.project_name}-${var.environment_name}-alb-security"
  description = "Security group for public-facing ALB"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTPS from internet"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTP from internet (redirects to HTTPS)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Outbound to containers"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr_block]
  }

  tags = {
    Name        = "${var.project_name}-${var.environment_name}-alb-sg"
    Environment = var.environment_name
    Project     = var.project_name
    SecurityTier = "public"
  }
}

# =============================================================================
# WAF Web Application Firewall
# =============================================================================

resource "aws_wafv2_web_acl" "api_firewall" {
  name        = "${var.project_name}-${var.environment_name}-api-waf"
  description = "WAF rules to protect API from common web exploits"
  scope       = "REGIONAL"

  default_action {
    allow {}
  }

  rule {
    name     = "AWS-AWSManagedRulesCommonRuleSet"
    priority = 10
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "AWSManagedRulesCommonRuleSet"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "AWS-AWSManagedRulesSQLiRuleSet"
    priority = 20
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesSQLiRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "AWSManagedRulesSQLiRuleSet"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "RateBasedRule"
    priority = 30
    action {
      block {}
    }
    statement {
      rate_based_statement {
        limit              = 1000
        aggregate_key_type = "IP"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "RateBasedRule"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.project_name}-${var.environment_name}-api-waf"
    sampled_requests_enabled   = true
  }
}

resource "aws_wafv2_web_acl_association" "api_waf_association" {
  resource_arn = aws_lb.main.arn
  web_acl_arn  = aws_wafv2_web_acl.api_firewall.arn
}

# =============================================================================
# AWS Shield DDoS Protection
# =============================================================================

resource "aws_shield_protection" "alb_shield_protection" {
  name         = "${var.project_name}-${var.environment_name}-alb-shield"
  resource_arn = aws_lb.main.arn
}

# =============================================================================
# Network ACLs - Additional Layer
# =============================================================================

resource "aws_network_acl" "private_subnet_nacl" {
  vpc_id     = aws_vpc.main.id
  subnet_ids = aws_subnet.private[*].id

  ingress {
    protocol   = "tcp"
    rule_no    = 100
    action     = "allow"
    cidr_block = "0.0.0.0/0"
    from_port  = 1024
    to_port    = 65535
  }

  egress {
    protocol   = "tcp"
    rule_no    = 100
    action     = "allow"
    cidr_block = "0.0.0.0/0"
    from_port  = 0
    to_port    = 65535
  }

  tags = {
    Name        = "${var.project_name}-${var.environment_name}-private-nacl"
    Environment = var.environment_name
    Project     = var.project_name
  }
}

# =============================================================================
# CloudTrail Audit Logging
# =============================================================================

resource "aws_cloudtrail" "api_audit_trail" {
  name                          = "${var.project_name}-${var.environment_name}-cloudtrail"
  s3_bucket_name                = aws_s3_bucket.cloudtrail_logs_bucket.id
  include_global_service_events = true
  is_multi_region_trail         = true
  enable_log_file_validation    = true
  kms_key_id                    = aws_kms_key.database_encryption_key.arn

  event_selector {
    read_write_type           = "All"
    include_management_events = true
  }

  tags = {
    Name        = "${var.project_name}-${var.environment_name}-cloudtrail"
    Environment = var.environment_name
    Project     = var.project_name
  }
}

resource "aws_s3_bucket" "cloudtrail_logs_bucket" {
  bucket        = "${var.project_name}-${var.environment_name}-cloudtrail-logs"
  force_destroy = false

  tags = {
    Name        = "${var.project_name}-${var.environment_name}-cloudtrail-logs"
    Environment = var.environment_name
    Project     = var.project_name
  }
}

resource "aws_s3_bucket_policy" "cloudtrail_bucket_policy" {
  bucket = aws_s3_bucket.cloudtrail_logs_bucket.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AWSCloudTrailAclCheck"
        Effect = "Allow"
        Principal = {
          Service = "cloudtrail.amazonaws.com"
        }
        Action   = "s3:GetBucketAcl"
        Resource = aws_s3_bucket.cloudtrail_logs_bucket.arn
      },
      {
        Sid    = "AWSCloudTrailWrite"
        Effect = "Allow"
        Principal = {
          Service = "cloudtrail.amazonaws.com"
        }
        Action   = "s3:PutObject"
        Resource = "${aws_s3_bucket.cloudtrail_logs_bucket.arn}/AWSLogs/${var.aws_account_id}/*"
        Condition = {
          StringEquals = {
            "s3:x-amz-acl" = "bucket-owner-full-control"
          }
        }
      }
    ]
  })
}

resource "aws_s3_bucket_public_access_block" "cloudtrail_block_public" {
  bucket = aws_s3_bucket.cloudtrail_logs_bucket.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# =============================================================================
# AWS Config Compliance
# =============================================================================

resource "aws_config_configuration_recorder" "compliance_recorder" {
  name     = "${var.project_name}-${var.environment_name}-config-recorder"
  role_arn = aws_iam_role.config_recorder_role.arn

  recording_group {
    all_supported                 = true
    include_global_resource_types = true
  }
}

resource "aws_iam_role" "config_recorder_role" {
  name = "${var.project_name}-${var.environment_name}-config-recorder-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "config.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "config_recorder_policy" {
  role       = aws_iam_role.config_recorder_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWS_ConfigRole"
}

resource "aws_config_delivery_channel" "compliance_delivery_channel" {
  name           = "${var.project_name}-${var.environment_name}-config-delivery"
  s3_bucket_name = aws_s3_bucket.config_logs_bucket.id
  s3_key_prefix  = "config"

  depends_on = [aws_config_configuration_recorder.compliance_recorder]
}

resource "aws_s3_bucket" "config_logs_bucket" {
  bucket        = "${var.project_name}-${var.environment_name}-config-logs"
  force_destroy = false

  tags = {
    Name        = "${var.project_name}-${var.environment_name}-config-logs"
    Environment = var.environment_name
    Project     = var.project_name
  }
}

# =============================================================================
# GuardDuty Threat Detection
# =============================================================================

resource "aws_guardduty_detector" "threat_detection" {
  enable = true

  datasources {
    s3_logs {
      enable = true
    }
  }

  tags = {
    Name        = "${var.project_name}-${var.environment_name}-guardduty"
    Environment = var.environment_name
    Project     = var.project_name
  }
}

# =============================================================================
# Security Hub Compliance Standards
# =============================================================================

resource "aws_securityhub_account" "security_standards" {
  enable_default_standards = true
}

resource "aws_securityhub_standards_subscription" "cis_aws_foundations" {
  standards_arn = "arn:aws:securityhub:${var.aws_region}::standards/cis-aws-foundations-benchmark/v/1.4.0"
  depends_on    = [aws_securityhub_account.security_standards]
}

resource "aws_securityhub_standards_subscription" "pci_dss" {
  standards_arn = "arn:aws:securityhub:${var.aws_region}::standards/pci-dss/v/3.2.1"
  depends_on    = [aws_securityhub_account.security_standards]
}