# Delivery status

This repository implements the local software foundation of the original AI Agent Reliability Lab blueprint. It does not turn a twelve-week research/adoption programme into completed external achievements.

| Area | v0.1 status | Remaining work |
|---|---|---|
| Recorder/replay | Implemented, Python and typed Node recorder | More native framework tracing, exact sensitive-value replay under controlled storage |
| Fault library | 20 bounded faults; seeded call-level SDK and local JSON proxy | Stream-level truncation/disconnect, realistic dependency traces, fault composition |
| Statistical profiles | Operational four-dimension scores, cluster bootstrap, regression gate | Full paper replication, broader task diversity, statistical power analysis |
| German modules | Rule checks, data-pattern findings, evidence ZIP, endpoint declarations, euro scenarios | Human-labelled German benchmark, privacy expert review, real enterprise tasks |
| Integrations | LangGraph, OpenAI Agents, MCP tool boundaries; compatible HTTP model API; OTel export | Claude/CrewAI native hooks and full provider tracing; standalone collector |
| Storage | SQLite, JSONL, DuckDB-to-Parquet export | Hosted Postgres/object storage, authentication, retention and multi-tenant access |
| Execution | Bounded in-process workers; non-root Docker image and CI test | Hardened hostile-agent isolation, distributed workers, real spend accounting |
| Ratings explorer | Live static fixture dashboard and reproducible data generator | Independently reproduce and rate 10–15 public agents with source revisions |
| Research | Protocol and fixture experiment are documented | Real models, calibrated judges, held-out human labels, original study and preprint |
| Adoption/publication | Open repository, CI, release artifacts, contribution templates | Company pilots, independent case studies, maintainer-acknowledged findings, talks |

Next experiments should freeze a public agent commit and task dataset, record model/provider/region declarations, run baseline and faults with independent outcome checks, inspect harms, and publish scripts/traces subject to data-review constraints. Report defects responsibly before publishing identifiable findings. No external bugs, users, merged fixes, paper, testimonials, or hiring outcomes are claimed.
