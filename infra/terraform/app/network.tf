locals {
  service_name = "${var.project_name}-${var.environment}"
  selected_azs = slice(sort(data.aws_availability_zones.available.names), 0, 2)
  subnet_az_indexes = {
    for index, availability_zone in local.selected_azs : availability_zone => index
  }

  secret_parameter_arns = [
    for parameter_name in [
      var.discord_token_parameter_name,
      var.gemini_api_key_parameter_name,
    ] : "arn:${data.aws_partition.current.partition}:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter${parameter_name}"
  ]
}

resource "aws_vpc" "bot" {
  cidr_block           = var.vpc_cidr_block
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "${local.service_name}-vpc"
  }
}

resource "aws_internet_gateway" "bot" {
  vpc_id = aws_vpc.bot.id

  tags = {
    Name = "${local.service_name}-igw"
  }
}

resource "aws_subnet" "public" {
  for_each = local.subnet_az_indexes

  vpc_id                  = aws_vpc.bot.id
  availability_zone       = each.key
  cidr_block              = cidrsubnet(var.vpc_cidr_block, 8, each.value)
  map_public_ip_on_launch = true

  tags = {
    Name = "${local.service_name}-public-${each.value + 1}"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.bot.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.bot.id
  }

  tags = {
    Name = "${local.service_name}-public"
  }
}

resource "aws_route_table_association" "public" {
  for_each = aws_subnet.public

  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

resource "aws_security_group" "bot" {
  name        = "${local.service_name}-task"
  description = "Outbound-only network access for the Discord translation bot."
  vpc_id      = aws_vpc.bot.id

  ingress = []
  egress  = []

  tags = {
    Name = "${local.service_name}-task"
  }

  lifecycle {
    ignore_changes = [egress]
  }
}

resource "aws_vpc_security_group_egress_rule" "https" {
  security_group_id = aws_security_group.bot.id
  description       = "HTTPS for Discord, translation/TTS services, and AWS APIs."
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "discord_voice" {
  security_group_id = aws_security_group.bot.id
  description       = "Outbound UDP for Discord voice media sessions."
  ip_protocol       = "udp"
  from_port         = 1024
  to_port           = 65535
  cidr_ipv4         = "0.0.0.0/0"
}
