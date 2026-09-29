variable "region" {
  type    = string
  default = "us-east-2"
}
variable "project" {
  type    = string
  default = "eia-documentdb"
}
variable "trusted_cidr" {
  type        = string
  description = "Your public IPv4 /32 for SSH"
}
variable "key_name" {
  type        = string
  description = "Existing EC2 key pair name"
}
variable "docdb_username" {
  type    = string
  default = "labadmin"
}
variable "docdb_password" {
  type        = string
  sensitive   = true
  description = "Pass through TF_VAR_docdb_password; never commit"
}
variable "docdb_instance_class" {
  type    = string
  default = "db.serverless"
}
variable "tags" {
  type = map(string)
  default = {
    Project     = "EIA-AWS-Activity"
    Environment = "Lab"
    ManagedBy   = "OMP"
    Point       = "3"
  }
}
