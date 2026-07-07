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
