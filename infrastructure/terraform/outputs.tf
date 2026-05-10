output "vpc_id" {
  value = aws_vpc.main.id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "database_subnet_ids" {
  value = aws_subnet.database[*].id
}

output "database_endpoint" {
  value     = aws_db_instance.postgres_database.endpoint
  sensitive = true
}

output "database_name" {
  value = var.postgres_database_name
}

output "load_balancer_dns_name" {
  value = aws_lb.main.dns_name
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  value = aws_ecs_service.api.name
}

output "ecr_repository_url" {
  value = aws_ecr_repository.api_repository.repository_url
}

output "cloudwatch_log_group" {
  value = aws_cloudwatch_log_group.api_log_group.name
}