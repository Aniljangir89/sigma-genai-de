import os, duckdb
from typing import TypedDict
from langgraph.graph import StateGraph, END

# Ensure the DB path is correctly set
DB_PATH = os.path.join(os.path.dirname(__file__), "sigma_platform.duckdb")

# ── STEP 1: Define the shared state ───────────────────────────────────────────
class CheckerState(TypedDict):
    sql          : str    # the SQL query to check
    is_safe      : bool   # True if the SQL has a WHERE clause
    check_reason : str    # one sentence: why it is safe or not
    result       : str    # query result (if safe) or blocked message (if not)


# ── STEP 2: sql_checker_node ──────────────────────────────────────────────────
def sql_checker_node(state: CheckerState) -> dict:
    """Check the SQL for a WHERE clause."""
    is_safe = "WHERE" in state["sql"].upper()
    reason = "Safe: WHERE clause found." if is_safe else "Unsafe: No WHERE clause found."
    return {"is_safe": is_safe, "check_reason": reason}


# ── STEP 3: safe_executor_node ────────────────────────────────────────────────
def safe_executor_node(state: CheckerState) -> dict:
    """Executes SQL if safe, otherwise returns blocked message."""
    if state["is_safe"]:
        try:
            with duckdb.connect(DB_PATH, read_only=True) as con:
                res = con.execute(state["sql"]).fetchall()
                return {"result": str(res)}
        except Exception as e:
            return {"result": f"ERROR: {str(e)}"}
    else:
        return {"result": "BLOCKED: " + state["check_reason"]}


# ── STEP 4: Routing function ──────────────────────────────────────────────────
def route_by_safety(state: CheckerState) -> str:
    """Return the next node based on safety status."""
    return "execute" if state["is_safe"] else "blocked"


# ── STEP 5: Build and wire the graph ─────────────────────────────────────────
def build_checker_graph():
    g = StateGraph(CheckerState)

    # Add nodes
    g.add_node("check", sql_checker_node)
    g.add_node("execute", safe_executor_node)
    g.add_node("blocked", safe_executor_node)

    # Set the entry point
    g.set_entry_point("check")

    # Add conditional edges
    g.add_conditional_edges(
        "check",
        route_by_safety,
        {"execute": "execute", "blocked": "blocked"}
    )

    # Both paths end at END
    g.add_edge("execute", END)
    g.add_edge("blocked", END)

    return g.compile()


# ── STEP 6: Run the tests ─────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "="*70)
    print("LAB 2 STUDENT BUILD — SQL Safety Graph")
    print("="*70)

    app = build_checker_graph()

    safe_sql   = "SELECT merchant_id, COUNT(*) AS txn_count FROM silver_transactions WHERE amount > 100 GROUP BY 1 ORDER BY 2 DESC LIMIT 5"
    unsafe_sql = "SELECT * FROM silver_transactions"

    for label, sql in [("✅ SAFE SQL (has WHERE)", safe_sql),
                       ("❌ UNSAFE SQL (no WHERE)", unsafe_sql)]:
        print(f"\n── {label} ──────────────────────────────────────────────")
        print(f"  SQL: {sql[:80]}...")
        init  = {"sql": sql, "is_safe": False, "check_reason": "", "result": ""}
        final = app.invoke(init)
        print(f"  is_safe      : {final['is_safe']}")
        print(f"  check_reason : {final['check_reason']}")
        print(f"  result       : {final['result'][:150]}")

    print("\n" + "─"*60)
    print("DEBRIEF — answer both before Lab 3:")
    print("─"*60)
    q1 = input('1. add_conditional_edges takes a dict {"execute": "execute", "blocked": "blocked"}.\n   What does this dict do? Why is it needed? ').strip()
    q2 = input('2. Both paths use the same function (safe_executor_node) but different node names.\n   Why not just one node for both paths? ').strip()

    print("\n✅ Build task complete. Show the trainer this output before Lab 3.")
    print(f"\nYour answers:")
    print(f"  Q1: {q1 or 'NOT ANSWERED'}")
    print(f"  Q2: {q2 or 'NOT ANSWERED'}")