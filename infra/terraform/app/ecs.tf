resource "aws_ecs_cluster" "bot" {
  name = local.service_name

  setting {
    name  = "containerInsights"
    value = "disabled"
  }

  tags = {
    Name = local.service_name
  }
}

resource "aws_cloudwatch_log_group" "bot" {
  name              = "/ecs/${local.service_name}"
  retention_in_days = 14

  tags = {
    Name = "/ecs/${local.service_name}"
  }
}

resource "aws_ecs_task_definition" "bot" {
  family                   = local.service_name
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = tostring(var.task_cpu)
  memory                   = tostring(var.task_memory)
  execution_role_arn       = aws_iam_role.execution.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name        = local.service_name
      image       = "${aws_ecr_repository.bot.repository_url}:${var.image_tag}"
      essential   = true
      stopTimeout = 30
      environment = [
        {
          name  = "SHUTDOWN_TIMEOUT_SECONDS"
          value = "20"
        }
      ]
      secrets = [
        {
          name      = "DISCORD_TOKEN"
          valueFrom = local.secret_parameter_arns[0]
        },
        {
          name      = "GEMINI_API_KEY"
          valueFrom = local.secret_parameter_arns[1]
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.bot.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "bot"
        }
      }
    }
  ])

  tags = {
    Name = local.service_name
  }
}

resource "aws_ecs_service" "bot" {
  name             = local.service_name
  cluster          = aws_ecs_cluster.bot.arn
  task_definition  = aws_ecs_task_definition.bot.arn
  desired_count    = var.desired_count
  launch_type      = "FARGATE"
  platform_version = "1.4.0"

  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = [for subnet in aws_subnet.public : subnet.id]
    security_groups  = [aws_security_group.bot.id]
    assign_public_ip = true
  }

  enable_ecs_managed_tags = true
  propagate_tags          = "SERVICE"

  depends_on = [aws_iam_role_policy.execution]

  tags = {
    Name = local.service_name
  }
}
