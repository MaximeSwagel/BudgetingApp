# App instance: public web traffic only. No SSH port open — shell access goes
# through SSM Session Manager (via the instance IAM role), so there's no key to
# manage and nothing to brute-force on port 22.
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
