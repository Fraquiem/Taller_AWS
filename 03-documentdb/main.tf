terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.33, < 7.0"
    }
  }
}

provider "aws" {
  region = var.region
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
    name   = "architecture"
    values = ["x86_64"]
  }
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, 2)
}

resource "aws_vpc" "lab" {
  cidr_block           = "10.63.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = var.tags
}
resource "aws_internet_gateway" "lab" {
  vpc_id = aws_vpc.lab.id
  tags   = var.tags
}
resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.lab.id
  cidr_block              = "10.63.1.0/24"
  availability_zone       = local.azs[0]
  map_public_ip_on_launch = true
  tags                    = merge(var.tags, { Name = "${var.project}-public" })
}
resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.lab.id
  cidr_block        = "10.63.${count.index + 10}.0/24"
  availability_zone = local.azs[count.index]
  tags              = merge(var.tags, { Name = "${var.project}-private-${count.index + 1}" })
}
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.lab.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.lab.id
  }
  tags = var.tags
}
resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

resource "aws_security_group" "bastion" {
  name_prefix = "${var.project}-bastion-"
  description = "SSH only from operator CIDR"
  vpc_id      = aws_vpc.lab.id
  ingress {
    protocol    = "tcp"
    from_port   = 22
    to_port     = 22
    cidr_blocks = [var.trusted_cidr]
  }
  egress {
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = var.tags
}
resource "aws_security_group" "docdb" {
  name_prefix = "${var.project}-docdb-"
  description = "DocumentDB only from bastion"
  vpc_id      = aws_vpc.lab.id
  ingress {
    protocol        = "tcp"
    from_port       = 27017
    to_port         = 27017
    security_groups = [aws_security_group.bastion.id]
  }
  egress {
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = var.tags
}

resource "aws_db_subnet_group" "docdb" {
  name       = var.project
  subnet_ids = aws_subnet.private[*].id
  tags       = var.tags
}
resource "aws_docdb_cluster_parameter_group" "lab" {
  family = "docdb5.0"
  name   = var.project
  parameter {
    name  = "tls"
    value = "enabled"
  }
  tags = var.tags
}
resource "aws_docdb_cluster" "lab" {
  cluster_identifier              = var.project
  engine                          = "docdb"
  engine_version                  = "5.0.0"
  master_username                 = var.docdb_username
  master_password                 = var.docdb_password
  db_subnet_group_name            = aws_db_subnet_group.docdb.name
  db_cluster_parameter_group_name = aws_docdb_cluster_parameter_group.lab.name
  vpc_security_group_ids          = [aws_security_group.docdb.id]
  storage_type                    = "standard"
  serverless_v2_scaling_configuration {
    min_capacity = 0.5
    max_capacity = 1.0
  }
  storage_encrypted   = true
  skip_final_snapshot = true
  deletion_protection = false
  tags                = var.tags
}
resource "aws_docdb_cluster_instance" "writer" {
  identifier                 = "${var.project}-writer"
  cluster_identifier         = aws_docdb_cluster.lab.id
  instance_class             = var.docdb_instance_class
  engine                     = aws_docdb_cluster.lab.engine
  auto_minor_version_upgrade = true
  tags                       = var.tags
}

resource "aws_secretsmanager_secret" "docdb" {
  name_prefix = "${var.project}-"
  description = "DocumentDB lab credentials; generated outside source control"
  tags        = var.tags
}
resource "aws_secretsmanager_secret_version" "docdb" {
  secret_id     = aws_secretsmanager_secret.docdb.id
  secret_string = jsonencode({ username = var.docdb_username, password = var.docdb_password })
}
resource "aws_instance" "bastion" {
  ami                         = data.aws_ami.al2023.id
  instance_type               = "t3.micro"
  subnet_id                   = aws_subnet.public.id
  associate_public_ip_address = true
  key_name                    = var.key_name
  vpc_security_group_ids      = [aws_security_group.bastion.id]
  metadata_options {
    http_tokens   = "required"
    http_endpoint = "enabled"
  }
  root_block_device {
    encrypted             = true
    volume_type           = "gp3"
    volume_size           = 8
    delete_on_termination = true
  }
  tags = merge(var.tags, { Name = "${var.project}-bastion" })
}
