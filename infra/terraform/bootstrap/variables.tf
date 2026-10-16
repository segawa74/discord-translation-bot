variable "aws_region" {
  description = "AWS region in which to create the Terraform state bucket."
  type        = string
  default     = "ap-northeast-1"
}

variable "project_name" {
  description = "Project tag applied to the state bucket."
  type        = string
  default     = "discord-translation-bot"
}

variable "state_bucket_name" {
  description = "Globally unique S3 bucket name for application Terraform state."
  type        = string

  validation {
    condition = (
      length(var.state_bucket_name) >= 3 &&
      length(var.state_bucket_name) <= 63 &&
      can(regex("^[a-z0-9][a-z0-9.-]*[a-z0-9]$", var.state_bucket_name)) &&
      !strcontains(var.state_bucket_name, "..")
    )
    error_message = "state_bucket_name must be a 3-63 character, lowercase S3 bucket name without consecutive periods."
  }
}
