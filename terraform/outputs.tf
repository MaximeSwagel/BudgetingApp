output "app_public_ip" {
  description = "Stable Elastic IP — survives instance replacement"
  value       = aws_eip.app.public_ip
}

output "app_instance_id" {
  value = aws_instance.app.id
}

output "db_endpoint" {
  value = aws_db_instance.postgres.address
}

output "ecr_backend_url" {
  value = aws_ecr_repository.backend.repository_url
}

output "ecr_frontend_url" {
  value = aws_ecr_repository.frontend.repository_url
}

output "github_actions_role_arn" {
  description = "Paste this into the GitHub Actions workflow's role-to-assume"
  value       = aws_iam_role.github_actions_deploy.arn
}
