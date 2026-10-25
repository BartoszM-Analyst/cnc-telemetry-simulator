# Module 1: ingestion endpoint. Every plant gateway is an IoT "thing" with its own X.509 certificate.
# The gateway proves who it is with that certificate (mutual TLS) and may only publish its own topics.

resource "aws_iot_thing" "gateway" {
  for_each = var.gateways
  name     = each.key

  attributes = {
    plant = each.value
  }
}

# AWS creates the key pair and signs the certificate. Note: the private key is then stored in the
# Terraform state file, one more reason terraform.tfstate must never be committed (see module 0, question 1).
resource "aws_iot_certificate" "gateway" {
  for_each = var.gateways
  active   = true
}

resource "aws_iot_thing_principal_attachment" "gateway" {
  for_each  = var.gateways
  thing     = aws_iot_thing.gateway[each.key].name
  principal = aws_iot_certificate.gateway[each.key].arn
}

# One policy for all gateways, made specific by policy variables:
# ${iot:Connection.Thing.ThingName} is replaced at connect time by the thing the certificate belongs to.
# So gw-plant-1 can connect only as client "gw-plant-1" and publish only under cnc-sim/gw-plant-1/...
# ($$ escapes the dollar sign so Terraform does not try to interpolate it.)
resource "aws_iot_policy" "gateway" {
  name = "${local.prefix}-gateway"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Action    = "iot:Connect"
        Resource  = "arn:aws:iot:${var.region}:${local.account_id}:client/$${iot:Connection.Thing.ThingName}"
        Condition = { Bool = { "iot:Connection.Thing.IsAttached" = "true" } }
      },
      {
        Effect   = "Allow"
        Action   = "iot:Publish"
        Resource = "arn:aws:iot:${var.region}:${local.account_id}:topic/${local.prefix}/$${iot:Connection.Thing.ThingName}/*"
      }
    ]
  })
}

resource "aws_iot_policy_attachment" "gateway" {
  for_each = var.gateways
  policy   = aws_iot_policy.gateway.name
  target   = aws_iot_certificate.gateway[each.key].arn
}

# The account's MQTT endpoint (ATS = Amazon Trust Services certificate chain).
data "aws_iot_endpoint" "data" {
  endpoint_type = "iot:Data-ATS"
}

# Root certificate the gateway uses to check it really talks to AWS.
data "http" "amazon_root_ca" {
  url = "https://www.amazontrust.com/repository/AmazonRootCA1.pem"
}

# ---- files for the gateway simulator, written to aws/certs/ (git-ignored) ----

locals {
  certs_dir = abspath("${path.module}/../../certs")
}

resource "local_file" "root_ca" {
  filename = "${local.certs_dir}/AmazonRootCA1.pem"
  content  = data.http.amazon_root_ca.response_body
}

resource "local_file" "certificate" {
  for_each = var.gateways
  filename = "${local.certs_dir}/${each.key}.cert.pem"
  content  = aws_iot_certificate.gateway[each.key].certificate_pem
}

resource "local_sensitive_file" "private_key" {
  for_each        = var.gateways
  filename        = "${local.certs_dir}/${each.key}.private.key"
  content         = aws_iot_certificate.gateway[each.key].private_key
  file_permission = "0600"
}

resource "local_file" "gateway_config" {
  filename = "${local.certs_dir}/gateway-config.json"
  content = jsonencode({
    endpoint = data.aws_iot_endpoint.data.endpoint_address
    root_ca  = local_file.root_ca.filename
    gateways = {
      for g, _ in var.gateways : g => {
        certificate = local_file.certificate[g].filename
        private_key = local_sensitive_file.private_key[g].filename
      }
    }
  })
}
