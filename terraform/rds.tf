resource "random_password" "db" {
  length  = 24
  special = false # avoid characters that need URL-encoding in DATABASE_URL
}

resource "aws_db_subnet_group" "default" {
  name       = "${var.project_name}-db-subnets"
  subnet_ids = data.aws_subnets.default.ids

  tags = {
    Name = "${var.project_name}-db-subnets"
  }
}

resource "aws_db_instance" "postgres" {
  identifier     = "${var.project_name}-db"
  engine         = "postgres"
  engine_version = "16"

  instance_class    = var.db_instance_class
  allocated_storage = 20
  storage_type      = "gp2"

  db_name  = var.db_name
  username = var.db_username
  password = random_password.db.result

  db_subnet_group_name   = aws_db_subnet_group.default.name
  vpc_security_group_ids = [aws_security_group.db.id]
  publicly_accessible    = false

  backup_retention_period = 1
  skip_final_snapshot     = true
  multi_az                = false
  storage_encrypted       = true

  tags = {
    Name = "${var.project_name}-db"
  }
}

# Stored so the running app instance (and you, via the console/CLI) can fetch
# the DB password without it ever living in plaintext user-data or git.
resource "aws_ssm_parameter" "db_password" {
  name  = "/${var.project_name}/db_password"
  type  = "SecureString"
  value = random_password.db.result
}

resource "aws_ssm_parameter" "openai_api_key" {
  name  = "/${var.project_name}/openai_api_key"
  type  = "SecureString"
  value = var.openai_api_key == "" ? "unset" : var.openai_api_key
}
