data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

data "aws_caller_identity" "current" {}

data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  # AWS publishes kernel-6.1, 6.12 and 6.18 builds of each AL2023 release with
  # identical CreationDate, so the unpinned filter made most_recent flip between
  # them from run to run (on 2026-09-25 two plans minutes apart resolved to the
  # kernel-6.18 image and then the kernel-6.1 image). Pinned to 6.12, the kernel
  # line the live instance's AMI uses (al2023-ami-2023.12.20260706.1-kernel-6.12-x86_64).
  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-kernel-6.12-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}
