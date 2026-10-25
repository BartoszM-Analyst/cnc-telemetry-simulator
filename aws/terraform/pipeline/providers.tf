# The whole data pipeline lives in this one Terraform root, built up module by module.
# `terraform destroy` here removes all of it (the budget in 00-bootstrap stays).

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    http = {
      source  = "hashicorp/http"
      version = "~> 3.4"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.5"
    }
  }
}

provider "aws" {
  region  = var.region
  profile = var.aws_profile

  default_tags {
    tags = {
      project    = "cnc-telemetry-pipeline"
      managed_by = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  prefix     = "cnc-sim"
  account_id = data.aws_caller_identity.current.account_id
}
