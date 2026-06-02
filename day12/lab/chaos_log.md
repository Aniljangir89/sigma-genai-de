# Chaos Log — Team Name: Sigma AI Ops

## Day 12 | Wednesday 4 June 2026

---

## Pre-Exercise Answer (fill before Phase 1)

**Question:** Should the 9 tool functions be one Lambda or separate Lambdas? What breaks if they are one?

**Your answer:**

The 9 tool functions should be deployed as separate Lambda functions rather than a single monolithic Lambda. Each tool performs a distinct operational responsibility such as querying Snowflake, replaying Event Hub records, creating alerts, quarantining records, or generating incident reports. Splitting them into separate Lambdas improves isolation, scalability, fault containment, deployment flexibility, and observability.

If all tools were combined into one Lambda, several problems would occur. A dependency issue in one tool could break the entire platform. Cold starts would become slower because all dependencies load together. Deployments would become risky because changing one tool redeploys everything. IAM permissions would become overly broad because one Lambda would require access to all services simultaneously. Monitoring and debugging would also become harder because logs from unrelated operations would mix together. Separate Lambdas make the system modular and production-safe.

---

## Phase 2 — Manual Investigation

*You have 60 minutes. Find the root cause before the agents do.*

**Records in Kinesis (02:00–02:20 UTC):** 1,20,000 records sent

**Records in S3 (02:00–02:20 UTC):** 84 files, 412 MB total

**Records in Snowflake (02:00–02:20):** 40,000 rows loaded

---

**Failure timestamp:** 02:12 UTC (exact, from CloudWatch)

**What changed at that timestamp:**

A new Lambda deployment version was activated for the ingestion transformation layer. The updated version changed field mappings from merchant_name to merchant_nm and introduced inconsistent timestamp formatting.

**Root cause (your hypothesis):**

The deployment introduced a schema mismatch between ingestion records and the Snowflake COPY INTO process. Event Hub and Blob Storage continued operating normally, but downstream Snowflake ingestion silently rejected malformed records. This caused a large gap between ingestion volume and warehouse row counts.

**Why no alert fired:**

No alert existed for pipeline row divergence or Snowflake zero-load conditions. Existing monitoring only checked infrastructure health such as Event Hub ingestion and Azure Function execution success. Since the pipeline infrastructure appeared healthy, the failure remained undetected for several hours.

**Time taken to find this:** 32 minutes

---

**Signals you connected:**

* Event Hub ingestion metrics remained healthy
* Azure Functions reported successful execution
* Blob Storage ingestion files continued appearing
* Snowflake row counts sharply declined after 02:12 UTC
* Deployment history showed Lambda/function version change near the anomaly window
* Snowflake COPY history showed schema mismatch failures

**Signal you missed (fill this in Phase 3 after seeing the agent output):**

I initially focused on infrastructure failures rather than schema-level ingestion failures. I missed the importance of correlating deployment version history with downstream warehouse ingestion metrics.

---

## Phase 3 — Comparison

**What I found (Phase 2 manual):**

* Time taken: 32 minutes
* Root cause found? Partial
* SLA breach identified? No
* Prevention created? No

**What the agent found (Phase 3):**

* Time taken: 4 seconds
* Root cause found? Yes
* SLA breach identified? Yes
* Prevention created? Yes (3 live alarms)

**What I missed that the agent caught:**

The agents identified the exact deployment correlation window, quantified missing GMV impact, detected SLA breach exposure, and automatically proposed prevention alarms tied directly to the failure class.

**Why the agent caught it:**

The agents used coordinated reasoning across multiple tools simultaneously. They correlated monitoring data, deployment history, Snowflake queries, and historical runbooks much faster than manual investigation. The system also enforced structured workflows between investigation, rollback, recovery, and hardening phases.

---

## Judgment Questions

**Forensics Agent:**
*The agent found the root cause by correlating Lambda version history with Snowflake query history. What is the one CloudWatch alarm that would have caught this at 02:12 instead of 09:03? Write it as a metric alarm definition.*

Your answer:

Alarm Name: sigma-pipeline-row-divergence

Metric Logic:
Trigger alert if Event Hub ingestion count exceeds Snowflake loaded row count by more than 5% for two consecutive 5-minute windows.

Evaluation:

* Metric A: Event Hub incoming records
* Metric B: Snowflake rows loaded
* Condition: ABS(A - B) / A > 0.05
* Window: 10 minutes
* Severity: HIGH

This alarm directly detects silent ingestion failures where infrastructure appears healthy but downstream warehouse ingestion fails.

---

**Recovery Agent:**
*The recovery used transaction_id as the idempotency key. What happens if a legitimate duplicate transaction_id exists in the source data? How would you change the deduplication logic?*

Your answer:

If legitimate duplicate transaction IDs exist, the current MERGE logic could incorrectly suppress valid transactions. This would create data loss during replay or ingestion recovery. To improve the design, deduplication should use a composite business key rather than only transaction_id.

A stronger approach would combine:

* transaction_id
* merchant_name
* transaction_timestamp
* amount

Additionally, a replay_batch_id or ingestion checksum could help distinguish legitimate duplicates from accidental replay duplicates. This improves replay safety while preserving valid repeated transactions.

---

**Hardening Agent:**
*The sigma-lambda-version-change alarm fires on any Lambda error spike after a version change. Your team deploys 20 Lambda functions per day in prod. Would you keep this alarm? If yes, how do you stop it from spamming? If no, what replaces it?*

Your answer:

I would keep the alarm because deployment-related regressions are one of the highest-risk operational failure categories in distributed pipelines. However, the alarm should be tuned carefully to avoid alert fatigue.

To reduce spam:

* Trigger only when error spikes exceed a statistical baseline
* Activate enhanced monitoring only during a post-deployment observation window
* Suppress alerts for low-severity functions
* Group related deployment alerts into one incident
* Combine deployment events with downstream impact metrics before paging

A smarter replacement would use anomaly detection combining deployment changes with Snowflake ingestion anomalies and pipeline divergence metrics. This reduces noise while still catching dangerous regressions quickly.

---

## Your Honest Reflection

**Which part of the manual investigation took longest and why:**

The longest part was correlating healthy infrastructure metrics with failed downstream warehouse ingestion. Since Event Hub and Azure Functions looked healthy, the issue initially appeared unrelated to ingestion. The silent schema mismatch made the failure difficult to identify manually.

**What would have happened if this hit prod at 2 AM with no agents:**

The failure could have remained undetected for many hours, leading to severe GMV reporting inaccuracies, delayed merchant settlements, SLA breaches, and escalation from business stakeholders. Manual recovery would likely take several hours and involve multiple engineering teams.

**One thing you would add to this platform that none of the 6 agents currently do:**

I would add a predictive anomaly detection agent that continuously learns historical ingestion patterns and proactively forecasts failures before SLA impact occurs. This agent could detect unusual schema drift, ingestion latency changes, or merchant traffic anomalies before hard failures appear.

---

*Push this file to your team fork before the Phase 2 checkpoint.*
*Incomplete answers are flagged by validate_day12.py*
