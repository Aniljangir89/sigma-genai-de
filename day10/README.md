# Day 10 — Agentic AI for Data Engineering

## Overview

This day covers **Agentic AI** — building AI systems that can reason autonomously, use tools, query databases, review their own outputs, fix broken code, and remember past actions across multiple runs. All labs use the **Sigma DataTech Silver layer** (`sigma_platform.duckdb`) as the data source and **AWS Bedrock (Amazon Nova Pro / Nova Lite)** as the AI brain.

The labs are designed to be run **in order** — each lab shows you a new level of capability and explains *why* the next one exists.

---

## Lab Sequence

| Lab | File | Framework | Core Concept |
|-----|------|-----------|--------------|
| 1 | `1_react_agent.py` | Raw Python | ReAct loop from scratch |
| 2 | `2_langgraph_sql_agent.py` | LangGraph | 2-agent SQL generate → review → execute |
| 2b | `2b_student_build.py` | LangGraph | Student exercise: SQL safety graph |
| 3 | `3_crewai_de_team.py` | CrewAI | 3-agent data quality crew |
| 4 ★ | `4_stretch_goal_agent_memory.py` | Custom | Self-healing pipeline with persistent memory |

★ = stretch goal for fast finishers

---

## Quick Start

```bash
# Step 1 — Confirm your environment is ready
python tests/validate_day10.py

# Step 2 — Install dependencies
pip install -r lab/requirements.txt

# Step 3 — Run labs in order
cd lab/
python 1_react_agent.py
python 2_langgraph_sql_agent.py
python 3_crewai_de_team.py
python 4_stretch_goal_agent_memory.py   # stretch goal
```

---

## File-by-File Code Summary

---

### 🧪 `tests/validate_day10.py` — Environment Preflight Checker

**Purpose:** Run this *before* starting any lab to make sure your machine is ready.

**What it checks:**
- Python version is 3.10 or higher
- All required packages are installed: `boto3`, `duckdb`, `langgraph`, `langchain-core`, `crewai`, `litellm`
- AWS credentials are valid (calls AWS STS to verify your account)
- Bedrock access works for **Nova Pro** and **Nova Lite** models
- `sigma_platform.duckdb` database file exists and is readable
- `agent_outputs/` directory exists

**How it works:**  
For each check, it runs a small test (like `import boto3` or `bedrock.invoke_model(...)`) and prints ✅ or ❌. At the end it gives a pass/fail summary. If anything fails, fix it before running any lab.

**Run it with:**
```bash
python tests/validate_day10.py
```

---

### 🔬 Lab 1 — `lab/1_react_agent.py` — Build Your Own ReAct Agent From Scratch

**Mission:** The fraud team asks: *"Which 3 merchants had the most suspicious transaction patterns last month?"* Build an AI agent that answers this autonomously — no frameworks, just Python.

**What is a ReAct Agent?**  
ReAct stands for **Reasoning + Acting**. The agent follows a loop:
1. **Thought** → decides what to do next
2. **Action** → calls a tool (query DB, get schema, calculate)
3. **Observation** → gets the result back
4. Repeats until it has enough information, then gives a **Final Answer**

**Tools the agent can use:**
| Tool | What it does |
|------|-------------|
| `query_db(sql)` | Runs a SQL query against DuckDB, returns results |
| `get_schema()` | Returns all table names and column definitions |
| `calculate(expression)` | Safely evaluates a math expression (e.g. `12345 / 30`) |

**How the code works (step by step):**

1. **`call_bedrock(prompt)`** — Sends a message to Amazon Nova Pro and gets a text response back. This is the "brain" of the agent.

2. **`parse_agent_output(text)`** — The LLM returns free text like:
   ```
   Thought: I should check the schema first.
   Action: get_schema
   Input: 
   ```
   This function uses regex to pull out the Thought, Action, Input, and Final Answer from that text.

3. **`run_react_agent(question)`** — The main loop. It:
   - Sends the question + conversation history to Bedrock
   - Parses the response
   - Executes the tool if an action was chosen
   - Appends the observation back to the conversation
   - Repeats up to `MAX_ITER = 6` times
   - If max iterations hit, forces the agent to give its best answer

4. **Safety cap** — `MAX_ITER = 6` prevents infinite loops. Without this, an agent can keep calling tools forever.

5. **`student_build_task()`** — A hands-on exercise where you add a 4th tool called `flag_merchant` that:
   - Accepts a merchant ID and reason
   - Appends it to `flagged_merchants.json`
   - Returns a confirmation string
   - Must be registered in both `TOOLS` dict AND `TOOL_DESCRIPTIONS` (the LLM can only use tools it's told about!)

**Outputs:**
- `agent_outputs/react_trace.json` — every Thought/Action/Observation step
- `agent_outputs/react_answer.txt` — the agent's final answer

**Key lesson:** Building the loop manually is painful — that pain is exactly why LangGraph (Lab 2) exists.

---

### 🔀 Lab 2 — `lab/2_langgraph_sql_agent.py` — LangGraph SQL Agent with Memory

**Mission:** Rebuild the Lab 1 agent properly using LangGraph. Add a 2-agent review loop so no bad SQL ever reaches the database.

**The Problem with Lab 1:** The raw ReAct agent has no structured retry, no state persistence, and no way to prevent bad SQL from running.

**The Solution — 3-Node LangGraph:**
```
NL Question → [Agent 1: Generator] → [Agent 2: Reviewer] → [Executor]
                      ↑                      |
                      └── REJECTED (feedback)┘
                          (max 3 rounds)
```

**Key components:**

**`SQLAgentState` (TypedDict):**  
A shared "blackboard" that all 3 nodes read from and write to. It holds: the question, DB schema, current SQL, reviewer feedback, approval status, execution results, and the reasoning trace.

**Node 1 — `sql_generator_node`:**  
- Reads the DB schema and past memory context
- If previous SQL was rejected, reads the reviewer's feedback
- Asks Nova Pro to write production-ready DuckDB SQL
- Returns the generated SQL to the state

**Node 2 — `sql_reviewer_node`:**  
- Reads the generated SQL and the original question
- Checks for: correctness, NULL handling, date logic, aggregation bugs, full-table scans, double-counting from joins
- Returns `VERDICT: APPROVED` or `VERDICT: REJECTED` with specific issues
- Saves feedback to SQLite memory regardless of verdict

**Node 3 — `sql_executor_node`:**  
- Runs the approved SQL against DuckDB
- Converts the dataframe result to a readable string
- Calls Nova Pro again to write a natural language business answer
- Saves the query + result to persistent SQLite memory

**`route_after_review(state)` — Conditional Routing:**  
- If `approved = True` → go to executor
- If `review_rounds >= 3` → go to executor anyway (best effort)
- Otherwise → loop back to generator with feedback

**`AgentMemory` (SQLite):**  
Persists across Python runs. Stores past approved queries and reviewer feedback. On the next run, the Generator reads this memory and starts smarter — it won't repeat mistakes.

**Snowflake Swap:**  
There's a clearly marked comment block in the executor node — replace 4 lines to switch from DuckDB to Snowflake. The agents don't know or care which database runs the SQL.

**Student Build Task (`2b_student_build.py`):**  
Build a 2-node LangGraph from scratch:
- Node 1: Check if SQL has a WHERE clause (pure Python, no LLM needed)
- Node 2: Execute if safe, block if not
- Routing: `safe → execute → END` or `unsafe → blocked → END`

**Outputs:**
- `agent_outputs/langgraph_trace.json` — full graph execution log
- `agent_outputs/approved_queries.json` — only SQL that passed review
- `agent_memory.db` — SQLite memory (persists across runs!)

**Key lesson:** LangGraph gives you typed state, conditional routing, memory, multi-agent review, and structured retries — all the things the raw ReAct loop was missing.

---

### 🛡️ Lab 2b — `lab/2b_student_build.py` — Student SQL Safety Graph

**Purpose:** A completed student exercise that demonstrates the 3 core LangGraph concepts by building a simple SQL safety checker.

**What it does:**  
Checks whether a SQL query has a WHERE clause before running it. This prevents accidental full-table scans on a 4M-row table.

**The graph:**
```
[check node] → (safe?) → [execute node] → END
                        → [blocked node] → END
```

**Key code:**
- `CheckerState` — TypedDict with: sql, is_safe, check_reason, result
- `sql_checker_node` — checks if `"WHERE"` is in the SQL string, sets `is_safe`
- `safe_executor_node` — if safe, runs SQL against DuckDB; if blocked, returns a BLOCKED message
- `route_by_safety` — returns `"execute"` or `"blocked"` based on `is_safe`

**Test cases:**
- `SELECT merchant_id, COUNT(*) FROM silver_transactions WHERE amount > 100 ...` → ✅ SAFE, returns data
- `SELECT * FROM silver_transactions` → ❌ BLOCKED

**Key lesson:** The 3 LangGraph concepts — TypedDict state + node functions + conditional edges — are all you need. Everything else is just more of these 3.

---

### 👥 Lab 3 — `lab/3_crewai_de_team.py` — CrewAI Data Quality Crew

**Mission:** Replace a 3-hour manual Monday morning data quality report with a 3-agent AI crew. Each agent has a distinct personality that shapes how it works.

**The 3 Agents:**

| Agent | Role | Model | Personality |
|-------|------|-------|-------------|
| `data_scout` | Senior Data Quality Analyst | Nova Pro | Obsessed with completeness, thinks in SQL, has caught 3 production bugs |
| `sql_surgeon` | Principal Data Engineer | Nova Pro | Battle-hardened, always uses WHERE clauses, tests on 10 rows first |
| `quality_guardian` | Data Governance Lead | Nova Lite | Last line of defence, has seen 5 production incidents, extremely risk-averse |

**CrewAI vs LangGraph:**
- **LangGraph** = graph-first → you define nodes, edges, state explicitly
- **CrewAI** = people-first → you define roles, goals, tasks (feels like managing a team)

**How the code works:**

1. **`get_silver_snapshot()`** — Runs DuckDB queries to collect: row counts, null percentages, negative amounts, duplicate transaction IDs. This data is pre-loaded into the agents' task descriptions so they start with real context.

2. **`get_schema_str()`** — Fetches all table names and column types from DuckDB to give agents the schema.

3. **`task_scout`** — Tells the Data Scout to investigate:
   - NULL values in each column
   - Negative amounts
   - Duplicate transaction IDs
   - Statistical outliers (amounts 3x above average)
   - Future-dated transactions

4. **`task_surgeon`** — Takes the Scout's findings and writes:
   - Idempotent SQL fix queries (safe to run multiple times)
   - Always with WHERE clauses
   - Ordered from safest to riskiest
   - With ROLLBACK strategies for risky fixes

5. **`task_guardian`** — Reviews every fix query from the Surgeon:
   - Checks for missing/broad WHERE clauses
   - Verifies no unintended deletions
   - Assesses downstream Gold layer impact
   - Gives each fix: `SAFE TO RUN / REVIEW FURTHER / DO NOT RUN`
   - Produces a final data health score out of 10

6. **`dq_crew`** — Assembles all 3 agents + 3 tasks in `Process.sequential` (each agent waits for the previous one to finish).

**Student Build Task:**  
Add a **4th agent — Incident Reporter** who distils the Guardian's 500-word report into a 6-line Slack message:
```
*SIGMA DATATECH DATA QUALITY ALERT*
*Date:*    <today>
*Status:*  CRITICAL / WARNING / OK
*Issues:*  <N total — X critical, Y high>
*Top fix:* <one sentence>
*Next review:* <tomorrow>
```
Key: `context=[task_guardian]` is the wire that gives the reporter access to the Guardian's findings. Without it, the reporter has no data.

**Outputs:**
- `agent_outputs/crewai_dq_report.json` — full crew output
- `agent_outputs/crewai_fix_queries.sql` — extracted SQL fix statements

**Key lesson:** In CrewAI, the backstory is not decoration — it changes the LLM's output. The Surgeon's backstory says "never without a WHERE clause" → the model generates safer SQL.

---

### 🔧 Lab 4 ★ — `lab/4_stretch_goal_agent_memory.py` — Self-Healing Pipeline Agent

**Mission:** Build an agent that automatically fixes broken Python pipelines at 2 AM without waking anyone up. On the second run with the same error, it fixes it from memory with **zero LLM calls**.

**The Broken Pipeline:**  
A real Python script with 4 intentional bugs:
```python
total = df["amounts"].sum()          # Bug 1: wrong column name ("amounts" not "amount")
conn.execute("CREATE TABLE AS ...")  # Bug 2: can't CREATE TABLE on read-only conn
conn.execute("DROP TABLE report")    # Bug 3: conn already closed above
top = df2.iloc[0]["merchant"]        # Bug 4 (subtle): column is "merchant_id", not "merchant"
```

**How the Healing Loop works (`heal()` function):**

1. Run the broken pipeline in a **subprocess** (isolated — the healer never crashes even if the pipeline does)
2. If it fails → get the error message
3. Check `HealingMemory` SQLite for a known fix for this error pattern
4. If found in memory → apply cached fix (no LLM call!)
5. If not found → call Bedrock to diagnose and write a fix
6. Replace the broken code with the fixed code
7. Run again — repeat up to `MAX_HEAL_ATTEMPTS = 4` times
8. If all attempts fail → escalate (print a message; in production, this would page on-call)

**`HealingMemory` class (SQLite):**
- `_fingerprint(error)` — creates an MD5 hash of the last 3 lines of the error. Same type of error always gets the same fingerprint.
- `lookup(error)` — checks if we've successfully fixed this error before
- `save(...)` — records each fix attempt (success or failure)
- `recall_all()` — shows the healing history at startup

**`safe_run(code)` function:**  
Writes the code to a temp file, runs it as a subprocess with a 15-second timeout. Returns `(True, output)` or `(False, error_message)`. This isolation prevents the healer from crashing even if the pipeline has a catastrophic error.

**`ai_fix(broken_code, error)` function:**  
Sends the broken code + error message to Nova Pro with a system prompt that says: "Fix ALL bugs, not just the one causing this error. Return ONLY valid Python." Also makes a second lightweight call to get a one-sentence rationale for the fix.

**First run vs Second run:**
- **First run:** 3 bugs → 3 Bedrock calls → 3 diagnoses → pipeline fixed
- **Second run (same pipeline):** Error fingerprint matches cache → `[MEMORY] Known fix found!` → 0 Bedrock calls → pipeline fixed on attempt 1

**Student Build Task:**  
Write your own broken pipeline (`BROKEN_PIPELINE_V2`) with:
- 2 Python runtime bugs (will cause exceptions — agent CAN fix these)
- 1 SQL logic bug (produces wrong results silently — agent CANNOT fix this, no exception)

This teaches the most important safety lesson: **self-healing works for runtime errors. It is blind to logic bugs.**

**Outputs:**
- `agent_outputs/healing_log.json` — full repair history with timestamps
- `agent_outputs/patched_pipeline.py` — the agent-fixed pipeline code
- `agent_memory.db` — shared SQLite (same DB as Lab 2, adds `healing_history` table)

**Key lesson:** Self-healing is a win for infrastructure failures (bad connections, wrong column names). It is NOT a substitute for code review. An auto-patched pipeline can pass all tests and still return wrong financial data.

---

## Dependencies (`lab/requirements.txt`)

| Package | Used in |
|---------|---------|
| `boto3 >= 1.34.0` | All labs — calls AWS Bedrock |
| `duckdb >= 0.10.0` | All labs — queries the Sigma DataTech database |
| `langgraph >= 0.2.0` | Lab 2, 2b — the graph framework |
| `langchain-core >= 0.3.0` | Lab 2 — LangGraph dependency |
| `crewai >= 0.80.0` | Lab 3 — the crew framework |
| `litellm >= 1.40.0` | Lab 3 — CrewAI uses LiteLLM to call Bedrock |

---

## All Outputs

| File | Lab | What it contains |
|------|-----|-----------------|
| `agent_outputs/react_trace.json` | 1 | Every Thought/Action/Observation step + final answer |
| `agent_outputs/react_answer.txt` | 1 | The agent's final merchant analysis |
| `agent_outputs/langgraph_trace.json` | 2 | Full graph execution with all node states |
| `agent_outputs/approved_queries.json` | 2 | Only SQL queries that passed reviewer verification |
| `agent_outputs/crewai_dq_report.json` | 3 | Full 3-agent quality report with Guardian verdict |
| `agent_outputs/crewai_fix_queries.sql` | 3 | SQL fix statements with comments and rollback plans |
| `agent_outputs/healing_log.json` | 4 | Repair history — attempts, errors, cache hits |
| `agent_outputs/patched_pipeline.py` | 4 | The agent-fixed Python pipeline code |
| `agent_memory.db` | 2 + 4 | Shared SQLite — approved queries + healing fix cache |

---

## AWS Setup

Labs use **boto3 default credential chain**. Credentials are resolved in order:
1. Environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
2. `~/.aws/credentials` profile
3. EC2/ECS instance profile

**Region:** `us-east-1` (hardcoded — Nova Pro/Lite are only available here)

**Models used:**
- `amazon.nova-pro-v1:0` — Labs 1, 2, 3, 4 (primary agents — highest quality)
- `amazon.nova-lite-v1:0` — Lab 3 Quality Guardian (lower cost for simpler formatting tasks)

---

## Snowflake Swap (Lab 2)

Lab 2 includes a clearly marked Snowflake swap point in the executor node. To switch from DuckDB to Snowflake, uncomment the block and set:

```bash
export SNOWFLAKE_ACCOUNT=your_account
export SNOWFLAKE_USER=your_user
export SNOWFLAKE_PASSWORD=your_password
export SNOWFLAKE_DATABASE=SIGMA_SILVER
export SNOWFLAKE_SCHEMA=PUBLIC
```

The agents don't know or care which database runs the SQL — the swap is transparent.

---

## Common Errors and Fixes

| Error | Likely cause | Fix |
|-------|-------------|-----|
| `ModuleNotFoundError: crewai` | Not installed | `pip install crewai litellm` |
| `ModuleNotFoundError: langgraph` | Not installed | `pip install langgraph langchain-core` |
| `botocore.exceptions.NoCredentialsError` | AWS not configured | Run `aws configure` |
| `AccessDeniedException: bedrock` | Model access not enabled | Bedrock console → Model access → Enable Nova Pro |
| `duckdb.CatalogException` | Wrong table name in SQL | Run `get_schema` first, check exact table names |
| Agent loops without answering | MAX_ITER hit before Final Answer | Normal — check `react_trace.json` for best-effort answer |

---

## Key Concepts Summary

| Concept | Where used | Simple explanation |
|---------|-----------|-------------------|
| **ReAct loop** | Lab 1 | Agent thinks → acts → observes → repeats |
| **Tool registration** | Lab 1 | LLM can ONLY call tools listed in the system prompt |
| **LangGraph StateGraph** | Lab 2, 2b | Shared dictionary flows between nodes; routing decides what runs next |
| **TypedDict state** | Lab 2, 2b | Strict schema for what data nodes can read/write |
| **Conditional edges** | Lab 2, 2b | Graph route depends on state values (approved? retry? execute?) |
| **SQLite memory** | Lab 2, 4 | Agent memory that survives Python restarts |
| **CrewAI Agent** | Lab 3 | Role + Goal + Backstory = personality that shapes LLM output |
| **CrewAI Task context** | Lab 3 | `context=[prev_task]` is the wire that connects agents |
| **Error fingerprinting** | Lab 4 | MD5 of error lines → cache key for known fixes |
| **Subprocess isolation** | Lab 4 | Run broken code in child process so healer never crashes |
| **Self-healing limits** | Lab 4 | Can fix runtime errors (traceback = signal); CANNOT fix silent logic bugs |
