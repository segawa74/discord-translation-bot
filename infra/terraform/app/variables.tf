variable "aws_region" {
  description = "AWS region for the bot infrastructure."
  type        = string
  default     = "ap-northeast-1"
}

variable "project_name" {
  description = "Lowercase project prefix used in AWS resource names."
  type        = string
  default     = "discord-translation-bot"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,39}$", var.project_name))
    error_message = "project_name must be 2-40 lowercase letters, digits, or hyphens and start with a letter."
  }
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
  default     = "prod"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,9}$", var.environment))
    error_message = "environment must be 1-10 lowercase letters, digits, or hyphens and start with a letter."
  }
}

variable "vpc_cidr_block" {
  description = "IPv4 /16-/20 CIDR block for the bot VPC; two public subnets with /24-/28 prefixes are derived from it."
  type        = string
  default     = "10.40.0.0/16"

  validation {
    condition = (
      can(regex("^([0-9]{1,3}\\.){3}[0-9]{1,3}/(1[6-9]|20)$", var.vpc_cidr_block)) &&
      can(cidrsubnet(var.vpc_cidr_block, 8, 1))
    )
    error_message = "vpc_cidr_block must be a valid IPv4 /16 through /20 CIDR so the derived AWS subnets have /24 through /28 prefixes."
  }
}

variable "task_cpu" {
  description = "Fargate task CPU units. 256 is 0.25 vCPU."
  type        = number
  default     = 256

  validation {
    condition     = contains([256, 512, 1024, 2048, 4096], var.task_cpu)
    error_message = "task_cpu must be a valid Fargate CPU value."
  }
}

variable "task_memory" {
  description = "Fargate task memory in MiB; 1024 is 1 GiB for the default 256 CPU units."
  type        = number
  default     = 1024

  validation {
    condition = (
      (var.task_cpu == 256 && contains([512, 1024, 2048], var.task_memory)) ||
      (var.task_cpu == 512 && var.task_memory >= 1024 && var.task_memory <= 4096 && var.task_memory % 1024 == 0) ||
      (var.task_cpu == 1024 && var.task_memory >= 2048 && var.task_memory <= 8192 && var.task_memory % 1024 == 0) ||
      (var.task_cpu == 2048 && var.task_memory >= 4096 && var.task_memory <= 16384 && var.task_memory % 1024 == 0) ||
      (var.task_cpu == 4096 && var.task_memory >= 8192 && var.task_memory <= 30720 && var.task_memory % 1024 == 0)
    )
    error_message = "task_memory must be a supported Fargate memory size for the selected task_cpu."
  }
}

variable "desired_count" {
  description = "Number of running bot tasks. Keep at zero during initial provisioning, then set to one after publishing an image and creating SSM parameters."
  type        = number
  default     = 0

  validation {
    condition     = var.desired_count >= 0 && floor(var.desired_count) == var.desired_count
    error_message = "desired_count must be a non-negative integer."
  }
}

variable "image_tag" {
  description = "Unique immutable ECR image tag to deploy."
  type        = string
  default     = "bootstrap"

  validation {
    condition     = can(regex("^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$", var.image_tag))
    error_message = "image_tag must be a valid ECR tag of at most 128 characters."
  }
}

variable "discord_token_parameter_name" {
  description = "Name of the externally managed SSM SecureString parameter for DISCORD_TOKEN."
  type        = string
  default     = "/discord-translation-bot/prod/DISCORD_TOKEN"

  validation {
    condition     = startswith(var.discord_token_parameter_name, "/") && !strcontains(var.discord_token_parameter_name, "*")
    error_message = "The Discord token parameter name must be an absolute SSM parameter path without wildcards."
  }
}

variable "gemini_api_key_parameter_name" {
  description = "Name of the externally managed SSM SecureString parameter for GEMINI_API_KEY."
  type        = string
  default     = "/discord-translation-bot/prod/GEMINI_API_KEY"

  validation {
    condition     = startswith(var.gemini_api_key_parameter_name, "/") && !strcontains(var.gemini_api_key_parameter_name, "*")
    error_message = "The Gemini API key parameter name must be an absolute SSM parameter path without wildcards."
  }
}

variable "secret_kms_key_arn" {
  description = "Optional customer-managed KMS key ARN for the SecureString parameters. Leave empty to use the AWS-managed SSM key."
  type        = string
  default     = ""

  validation {
    condition     = var.secret_kms_key_arn == "" || can(regex("^arn:[^:]+:kms:[^:]+:[0-9]{12}:key/.+$", var.secret_kms_key_arn))
    error_message = "secret_kms_key_arn must be empty or a customer-managed KMS key ARN."
  }
}
