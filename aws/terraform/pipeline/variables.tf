variable "region" {
  description = "AWS region. New-style (project) accounts have a fixed region; this one is Stockholm."
  type        = string
  default     = "eu-north-1"
}

variable "aws_profile" {
  description = "AWS CLI profile Terraform uses (the credential_process profile, see aws/README.md)."
  type        = string
  default     = "cnc-sim-tf"
}

variable "gateways" {
  description = "One edge gateway (data-collection computer) per plant: gateway name => plant code."
  type        = map(string)
  default = {
    "gw-plant-1" = "plant-1"
    "gw-plant-2" = "plant-2"
    "gw-plant-3" = "plant-3"
  }
}
