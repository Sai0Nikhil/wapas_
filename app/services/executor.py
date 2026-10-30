"""Idempotent executor. TODO (hours 4-6).
Rule: insert Action(idempotency_key=f"case{case_id}:{kind}:{n}") FIRST; unique violation => already sent, skip."""
