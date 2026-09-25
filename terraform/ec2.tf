resource "aws_iam_role" "app_instance" {
  name = "${var.project_name}-app-instance-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# SSM Session Manager plus Run Command is the primary shell and deploy path:
# CI deploys via ssm:SendCommand and needs no SSH key or open port. SSH is an
# optional extra controlled by ssh_allowed_cidr and ssh_public_key.
resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.app_instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# Pull-only access to our ECR repos.
resource "aws_iam_role_policy_attachment" "ecr_read" {
  role       = aws_iam_role.app_instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

# AmazonSSMManagedInstanceCore only covers Session Manager connectivity, not
# Parameter Store reads — this grants read access to just this project's params.
resource "aws_iam_role_policy" "read_ssm_params" {
  name = "${var.project_name}-read-ssm-params"
  role = aws_iam_role.app_instance.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ssm:GetParameter", "ssm:GetParameters"]
      Resource = "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/${var.project_name}/*"
    }]
  })
}

resource "aws_iam_instance_profile" "app_instance" {
  name = "${var.project_name}-app-instance-profile"
  role = aws_iam_role.app_instance.name
}

# cloud-init installs this key at launch. That replaces the hand-edited
# authorized_keys the previous host relied on, so SSH access carries over when
# the instance is replaced.
resource "aws_key_pair" "ssh" {
  count      = var.ssh_public_key != "" ? 1 : 0
  key_name   = "${var.project_name}-ssh"
  public_key = var.ssh_public_key

  tags = {
    Name = "${var.project_name}-ssh"
  }
}

resource "aws_instance" "app" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.app_instance_type
  subnet_id              = data.aws_subnets.default.ids[0]
  vpc_security_group_ids = [aws_security_group.app.id]
  iam_instance_profile   = aws_iam_instance_profile.app_instance.name
  key_name               = one(aws_key_pair.ssh[*].key_name)

  user_data = templatefile("${path.module}/user_data.sh.tpl", {
    aws_region          = var.aws_region
    db_endpoint         = aws_db_instance.postgres.address
    db_port             = aws_db_instance.postgres.port
    db_name             = var.db_name
    db_username         = var.db_username
    db_ssm_param        = aws_ssm_parameter.db_password.name
    openai_ssm_param    = aws_ssm_parameter.openai_api_key.name
    anthropic_ssm_param = aws_ssm_parameter.anthropic_api_key.name
    base_currency       = var.base_currency
    ecr_backend         = aws_ecr_repository.backend.repository_url
    ecr_frontend        = aws_ecr_repository.frontend.repository_url
  })
  user_data_replace_on_change = true

  tags = {
    Name = "${var.project_name}-app"
  }

  # The AMI comes from a most_recent lookup that moves with every AL2023
  # release. Without ignore_changes, any plan after a new release would destroy
  # and recreate the host. A newer AMI is only picked up when the instance is
  # replaced for another reason (a user_data or key_name change), or
  # deliberately via `terraform apply -replace=aws_instance.app`. A replacement
  # launches with whatever the lookup currently returns.
  lifecycle {
    ignore_changes = [ami]
  }
}

# Stable public address that survives instance replacement — DNS/bookmarks
# keep working and nothing downstream has to learn a new IP.
resource "aws_eip" "app" {
  instance = aws_instance.app.id
  domain   = "vpc"

  tags = {
    Name = "${var.project_name}-app-eip"
  }
}
