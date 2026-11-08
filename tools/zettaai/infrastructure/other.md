# Other infrastructure repos

**GitHub:** https://github.com/orgs/ZettaAI/repositories
**Status:** as of 2026-11-06

| Repo | Kind | Notes |
|---|---|---|
| [samwise](https://github.com/ZettaAI/samwise) | original (2023) | run interruptible (preemptible) jobs in containers, syncing working dirs to cloud storage; used by DeepEM training Docker |
| [kombu-worker](https://github.com/ZettaAI/kombu-worker) | original (2024) | python-task-queue-style API over AMQP/RabbitMQ, for seuron |
| [python-task-queue](https://github.com/ZettaAI/python-task-queue) | fork | branch `nkem-gcp-pubsub`: GCP Pub/Sub backend (2020) |
| [procspec](https://github.com/ZettaAI/procspec) | original (2020) | YAML specification of computational tasks (precursor of the CUE specs) |
| [cloud-bot](https://github.com/ZettaAI/cloud-bot), [cloud-bot-workers](https://github.com/ZettaAI/cloud-bot-workers) | original (2020) | Slack bot dispatching cloud jobs via RabbitMQ |
| [CeleryMetricsExporter](https://github.com/ZettaAI/CeleryMetricsExporter) | mirror | Prometheus metrics for Celery |
| [igneous](https://github.com/ZettaAI/igneous), [seuron_deployment](https://github.com/ZettaAI/seuron_deployment) | mirrors | see [../../seung-lab/infrastructure/](../../seung-lab/infrastructure/) |
| [scipy](https://github.com/ZettaAI/scipy), [mypy](https://github.com/ZettaAI/mypy), [typeguard](https://github.com/ZettaAI/typeguard) | forks for upstream fixes | `nkem/fix-gh-24966`, constrained TypeVar decorators |
| [zettaai.github.io](https://github.com/ZettaAI/zettaai.github.io) | company site | services: stitching, alignment, cell segmentation, nucleus/vessel/compartment/organelle segmentation, synapse detection & assignment, CAVE proofreading; BRAIN CONNECTS contributor |
