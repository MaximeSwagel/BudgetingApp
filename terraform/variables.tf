variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "eu-north-1"
}

variable "project_name" {
  description = "Short name used to prefix/tag all resources"
  type        = string
  default     = "budgetingapp"
}

variable "app_instance_type" {
  description = "EC2 instance type for the app host (free-tier eligible in eu-north-1)"
  type        = string
  default     = "t3.micro"
}

variable "db_instance_class" {
  description = "RDS instance class (free-tier eligible)"
  type        = string
  default     = "db.t3.micro"
}

variable "db_name" {
  description = "Postgres database name"
  type        = string
  default     = "budgetingapp"
}

variable "db_username" {
  description = "Postgres master username"
  type        = string
  default     = "budget"
}

variable "github_repo" {
  description = "GitHub repo allowed to assume the CI/CD deploy role, in owner/repo form"
  type        = string
  default     = "MaximeSwagel/BudgetingApp"
}

variable "base_currency" {
  description = "App base currency, passed through to the backend container"
  type        = string
  default     = "ILS"
}

variable "openai_api_key" {
  description = "OpenAI API key for transaction categorization (optional; left blank, transactions just stay Uncategorized)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "anthropic_api_key" {
  description = "Anthropic API key for transaction categorization (optional; blank -> Claude just returns Uncategorized)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "openrouter_api_key" {
  description = "OpenRouter API key for Jev transaction categorization (optional; blank -> Jev just returns Uncategorized)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "ssh_allowed_cidr" {
  description = "Single IPv4 CIDR allowed to reach tcp/22 on the app instance. Empty means no port-22 rule at all, and SSM Session Manager remains the primary shell path. Set it in the git-ignored terraform/terraform.tfvars or via TF_VAR_ssh_allowed_cidr, and never commit it."
  type        = string
  default     = ""

  validation {
    condition     = var.ssh_allowed_cidr == "" || (can(cidrnetmask(var.ssh_allowed_cidr)) && !endswith(var.ssh_allowed_cidr, "/0"))
    error_message = "ssh_allowed_cidr must be empty or a single IPv4 CIDR such as 203.0.113.10/32, and a /0 range is refused because it would expose SSH to the whole internet."
  }
}

variable "ssh_public_key" {
  description = "OpenSSH public key line (the contents of a .pub file). It is registered as an EC2 key pair and attached to the app instance at launch, so SSH access survives instance replacement. Empty means no key pair. EC2 key pairs only take effect at launch, so setting or clearing this value forces instance replacement; to close SSH temporarily, clear ssh_allowed_cidr instead (an in-place SG change). Set it via terraform.tfvars or TF_VAR_ssh_public_key."
  type        = string
  default     = ""

  validation {
    condition     = var.ssh_public_key == "" || can(regex("^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(256|384|521)) [A-Za-z0-9+/]+=*( .*)?$", var.ssh_public_key))
    error_message = "ssh_public_key must be empty or a single-line OpenSSH public key such as ssh-ed25519 AAAA... comment."
  }
}
