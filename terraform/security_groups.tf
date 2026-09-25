# App instance: public web traffic on 80, 443 and 8080 (dev frontend).
# Shell access goes primarily through SSM Session Manager via the instance IAM
# role, with no key and no open port.
# SSH on tcp/22 is optional and off by default: the rule below exists only when
# var.ssh_allowed_cidr is set; see terraform.tfvars.example.
# The live rule was first added by hand in the console on 2026-08-01 and is now
# written in code.
resource "aws_security_group" "app" {
  name        = "${var.project_name}-app-sg"
  description = "Allow inbound HTTP/HTTPS, all outbound"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Dev frontend"
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  dynamic "ingress" {
    for_each = var.ssh_allowed_cidr == "" ? [] : [var.ssh_allowed_cidr]
    content {
      description = "SSH"
      from_port   = 22
      to_port     = 22
      protocol    = "tcp"
      cidr_blocks = [ingress.value]
    }
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-app-sg"
  }
}

# DB instance: only reachable from the app instance's security group, nothing else.
resource "aws_security_group" "db" {
  name        = "${var.project_name}-db-sg"
  description = "Allow inbound Postgres only from the app instance"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description     = "Postgres from app instance"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-db-sg"
  }
}
