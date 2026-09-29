output "bucket_name" { value = aws_s3_bucket.data.bucket }
output "instance_id" { value = aws_instance.lab.id }
output "instance_public_ip" { value = aws_instance.lab.public_ip }
output "rds_endpoint" { value = aws_db_instance.postgres.address }
output "rds_secret_arn" { value = aws_db_instance.postgres.master_user_secret[0].secret_arn }
output "region" { value = var.aws_region }
