# Security model

AgentGate treats model output, evaluation inputs, tool arguments, and GitHub
content as untrusted.

## What is executed

The deterministic policy agent calls a fixed tool registry:
`get_order`, `get_customer`, `check_return_policy`, `create_return`.
Any other name is refused. Arguments that are not short identifiers are
refused. Tool results do not leave the process, and `create_return` does not
mutate the fixture catalog.

Dataset-authored code tests are the only code execution path. The test source
comes from the evaluation dataset, which is project configuration, not from
the model. The model response is written to `payload.json` and read as data.
The container command is:

- `--network none`
- `--read-only`
- `--cap-drop ALL`
- `--security-opt no-new-privileges`
- `--user 65534:65534`
- memory, CPU, and pid limits
- a wall-clock timeout
- a temporary directory that is removed after the run

The command does not use `--privileged` and does not mount the Docker socket.
If Docker is missing, or the container fails to start, the case is an
infrastructure error. It is excluded from accuracy.

## What is not executed

Model text is never passed to `eval`, a shell, or a container entrypoint.
Harness files reject an `api_key` field. Credentials are read only from
environment variables. Reports store provider names and token counts, not
secrets.

Paths supplied to the API must resolve inside the repository root.

## What this does not provide

The HTTP API has no authentication. It is a local development service. Do not
expose it to a network you do not trust. The demonstration catalog is
synthetic. The Docker sandbox is the boundary for code tests; the policy
agent itself does not need Docker.
