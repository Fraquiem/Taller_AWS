terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile != "" ? var.aws_profile : null

  default_tags {
    tags = {
      Project     = "EIA-AWS-Activity"
      Environment = "Lab"
      ManagedBy   = "OMP"
    }
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }
  filter {
    name   = "state"
    values = ["available"]
  }
}

resource "random_id" "suffix" {
  byte_length = 4
}

variable "aws_region" {
  type    = string
  default = "us-east-2"
}
variable "aws_profile" {
  type    = string
  default = ""
}
variable "vpc_cidr" {
  type    = string
  default = "10.42.0.0/16"
}
variable "trusted_cidr" {
  type        = string
  default     = "127.0.0.1/32"
  description = "Replace only at apply time with your public /32 if SSH is needed."
}
variable "key_name" {
  type        = string
  default     = ""
  description = "Existing EC2 key pair; leave empty when using another access method."
}
variable "db_username" {
  type    = string
  default = "eiaadmin"
}
variable "db_name" {
  type    = string
  default = "eia"
}
