output "state_bucket_name" {
  description = "S3 bucket name to set in the application backend.hcl."
  value       = aws_s3_bucket.terraform_state.id
}

output "aws_region" {
  description = "AWS region containing the state bucket."
  value       = var.aws_region
}
