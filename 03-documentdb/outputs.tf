output "region" { value = var.region }
output "bastion_public_ip" { value = aws_instance.bastion.public_ip }
output "bastion_security_group_id" { value = aws_security_group.bastion.id }
output "docdb_endpoint" { value = aws_docdb_cluster.lab.endpoint }
output "docdb_port" { value = 27017 }
output "secret_arn" { value = aws_secretsmanager_secret.docdb.arn }
output "ssh_tunnel" { value = "ssh -i /path/key.pem -N -L 27018:${aws_docdb_cluster.lab.endpoint}:27017 ec2-user@${aws_instance.bastion.public_ip}" }
