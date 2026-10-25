variable "region" {
  description = "AWS region for the whole project. New-style (project) accounts have a fixed region; this one is Stockholm."
  type        = string
  default     = "eu-north-1"
}

variable "aws_profile" {
  description = "Named AWS CLI profile created with `aws configure --profile ...`."
  type        = string
  default     = "cnc-sim"
}

variable "monthly_limit_usd" {
  description = "Monthly budget in USD. The project normally costs far less."
  type        = string
  default     = "5"
}

variable "alert_email" {
  description = "Where budget alerts are sent. Set it in terraform.tfvars (that file is git-ignored)."
  type        = string
}
