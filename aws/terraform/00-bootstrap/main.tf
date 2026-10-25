# Module 0: account guard rails.
# Creates a monthly cost budget that e-mails you before the project costs real money.
# Run once per AWS account:  terraform init && terraform apply

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region  = var.region
  profile = var.aws_profile

  # Every resource gets these tags, so the project is easy to find and cost-track.
  default_tags {
    tags = {
      project    = "cnc-telemetry-pipeline"
      managed_by = "terraform"
    }
  }
}

resource "aws_budgets_budget" "monthly" {
  name         = "cnc-telemetry-monthly"
  budget_type  = "COST"
  limit_amount = var.monthly_limit_usd
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  # Warn at 50 % of actual spend ...
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 50
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }

  # ... and when AWS forecasts the month will exceed the limit.
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }
}
