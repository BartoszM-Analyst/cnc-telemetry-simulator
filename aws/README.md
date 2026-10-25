# AWS data pipeline

Cloud version of the project: plant gateways stream machine data over MQTT to AWS IoT, and the data
is refined through bronze, silver and gold layers before it reaches the dashboard. Built step by step;
this file grows with each module.

| Module | What it adds | Where |
|---|---|---|
| 0 | Monthly cost budget with e-mail alerts | `terraform/00-bootstrap/` |
| 1 | Gateway simulator (MQTT over mutual TLS), IoT things, certificates, least-privilege policy | `gateway/`, `terraform/pipeline/iot.tf` |

## Access

The account signs in with AWS Builder ID, so there are no long-lived access keys. The CLI uses
`aws login` (AWS CLI 2.32+), and Terraform reads the same session through a `credential_process` profile.
`~/.aws/config`:

```ini
[profile cnc-sim]
# written by: aws login --profile cnc-sim
region = eu-north-1

[profile cnc-sim-tf]
credential_process = aws configure export-credentials --profile cnc-sim --format process
region = eu-north-1
```

A session lasts at most 12 hours; run `aws login --profile cnc-sim` again when it expires.

## Run

```bash
cd aws/terraform/pipeline
terraform init
terraform apply          # IoT things, certificates, policy; writes aws/certs/ (git-ignored)

cd ../../..
pip install -r aws/gateway/requirements.txt
python aws/gateway/publish.py --dry-run                              # see the messages, no AWS
python aws/gateway/publish.py --start 06:00 --minutes 30 --speed 60   # 30 min of production in 30 s
```

Watch the stream in the AWS console: IoT Core → MQTT test client → subscribe to `cnc-sim/#`.

## Message format

Topic: `cnc-sim/<gateway>/<machine>/<telemetry|alarms>`, QoS 1.

```json
{"schema": "cnc-telemetry/v1", "message_id": "…", "gateway_id": "gw-plant-1", "machine_code": "CNC-01",
 "type": "telemetry", "recorded_at": "2026-10-25T05:00:00.239Z", "is_available": true,
 "execution_state": "ACTIVE", "spindle_rpm": 3200.0, "…": "…", "sent_at": "…"}
```

`message_id` is derived from machine, type and timestamp, so a redelivered message has the same id.
The replay deliberately adds about 0.5 % duplicates and 0.5 % late (out-of-order) messages, which the
silver layer has to handle.

## Clean up

```bash
cd aws/terraform/pipeline && terraform destroy
```
