resource "aws_iam_role" "execution" {
  name = "${local.service_name}-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })

  tags = {
    Name = "${local.service_name}-execution"
  }
}

locals {
  execution_policy_statements = concat(
    [
      {
        Sid      = "GetEcrAuthorizationToken"
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Sid    = "PullBotImage"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
        ]
        Resource = aws_ecr_repository.bot.arn
      },
      {
        Sid    = "WriteContainerLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "arn:${data.aws_partition.current.partition}:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:${aws_cloudwatch_log_group.bot.name}:log-stream:*"
      },
      {
        Sid      = "ReadRuntimeParameters"
        Effect   = "Allow"
        Action   = ["ssm:GetParameters"]
        Resource = local.secret_parameter_arns
      },
    ],
    var.secret_kms_key_arn == "" ? [] : [
      {
        Sid      = "DecryptRuntimeParameters"
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = var.secret_kms_key_arn
        Condition = {
          StringEquals = {
            "kms:ViaService" = "ssm.${var.aws_region}.${data.aws_partition.current.dns_suffix}"
          }
        }
      }
    ]
  )
}

resource "aws_iam_role_policy" "execution" {
  name = "${local.service_name}-execution"
  role = aws_iam_role.execution.id

  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = local.execution_policy_statements
  })
}
