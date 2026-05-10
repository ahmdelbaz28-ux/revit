terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0.0"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.5.0"
    }
  }
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "eu-west-2"
}

variable "environment_name" {
  description = "Environment name"
  type        = string
  default     = "production"
}

variable "project_name" {
  description = "Project name"
  type        = string
  default     = "firealarmai"
}

variable "vpc_cidr_block" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Availability zones"
  type        = list(string)
  default     = ["eu-west-2a", "eu-west-2b", "eu-west-2c"]
}

variable "private_subnet_cidrs" {
  description = "Private subnet CIDR blocks"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
}

variable "public_subnet_cidrs" {
  description = "Public subnet CIDR blocks"
  type        = list(string)
  default     = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]
}

variable "database_subnet_cidrs" {
  description = "Database subnet CIDR blocks"
  type        = list(string)
  default     = ["10.0.201.0/24", "10.0.202.0/24", "10.0.203.0/24"]
}

variable "postgres_engine_version" {
  description = "PostgreSQL engine version"
  type        = string
  default     = "15.5"
}

variable "postgres_instance_class" {
  description = "PostgreSQL instance class"
  type        = string
  default     = "db.t4g.medium"
}

variable "postgres_allocated_storage" {
  description = "PostgreSQL allocated storage in GB"
  type        = number
  default     = 100
}

variable "postgres_database_name" {
  description = "PostgreSQL database name"
  type        = string
  default     = "firealarmdb"
}

variable "postgres_master_username" {
  description = "PostgreSQL master username"
  type        = string
  default     = "firealarm_admin"
  sensitive   = true
}

variable "postgres_master_password" {
  description = "PostgreSQL master password"
  type        = string
  sensitive   = true
}

variable "container_cpu_limit" {
  description = "Container CPU limit"
  type        = string
  default     = "2048"
}

variable "container_memory_limit" {
  description = "Container memory limit in MiB"
  type        = string
  default     = "4096"
}

variable "container_desired_count" {
  description = "Number of container instances"
  type        = number
  default     = 2
}

variable "container_max_scaling_count" {
  description = "Maximum number of container instances"
  type        = number
  default     = 6
}

variable "container_min_scaling_count" {
  description = "Minimum number of container instances"
  type        = number
  default     = 2
}

variable "health_check_path" {
  description = "Health check endpoint"
  type        = string
  default     = "/healthz"
}

variable "github_repository_url" {
  description = "GitHub repository URL"
  type        = string
  default     = "https://github.com/ahmdelbaz28-ux/revit"
}

variable "github_branch_name" {
  description = "GitHub branch name"
  type        = string
  default     = "main"
}

variable "acm_certificate_arn" {
  description = "ACM certificate ARN for HTTPS"
  type        = string
  default     = ""
}