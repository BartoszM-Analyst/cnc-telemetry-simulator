output "iot_endpoint" {
  description = "MQTT endpoint the gateways connect to (port 8883)."
  value       = data.aws_iot_endpoint.data.endpoint_address
}

output "gateway_config_file" {
  description = "Config file the gateway simulator reads."
  value       = local_file.gateway_config.filename
}
