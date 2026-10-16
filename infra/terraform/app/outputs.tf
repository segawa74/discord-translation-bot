output "ecr_repository_url" {
  description = "ECR repository URL for building and pushing the bot image."
  value       = aws_ecr_repository.bot.repository_url
}

output "ecs_cluster_name" {
  description = "ECS cluster name."
  value       = aws_ecs_cluster.bot.name
}

output "ecs_service_name" {
  description = "ECS service name."
  value       = aws_ecs_service.bot.name
}

output "log_group_name" {
  description = "CloudWatch Logs group with a 14-day retention period."
  value       = aws_cloudwatch_log_group.bot.name
}
