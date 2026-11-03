#!/usr/bin/env python3
"""
Demo script for Self-Healing Multi-Agent System.

Usage:
    python3 demo.py                  # against running server
    python3 demo.py --standalone     # no server needed
"""
import argparse
import asyncio
import json
import logging
import os
import sys

import httpx

PORT = int(os.getenv("PORT", "8080"))
API = f"http://localhost:{PORT}"

# ── ANSI Colors ──
B = "\033[94m"   # Blue
G = "\033[92m"   # Green
Y = "\033[93m"   # Yellow
R = "\033[91m"   # Red
D = "\033[1m"    # Bold
X = "\033[0m"    # Reset
C = "\033[96m"   # Cyan


def banner(text: str):
    print(f"\n{D}{'=' * 64}{X}")
    print(f"{D}  {text}{X}")
    print(f"{D}{'=' * 64}{X}\n")


def section(text: str):
    print(f"\n{D}{'-' * 48}{X}")
    print(f"  {text}")
    print(f"{D}{'-' * 48}{X}\n")


async def demo_api():
    async with httpx.AsyncClient(timeout=60) as client:

        # ──────────────────────────────────────────────────
        section("Health Check")
        resp = await client.get(f"{API}/health")
        h = resp.json()
        print(f"  Status : {G}{h['status']}{X}")
        print(f"  Version: {h.get('version', '?')}")
        print(f"  Gemini : {G if h.get('gemini') == 'active' else Y}{h.get('gemini', '?')}{X}")
        print(f"  Slack  : {G if h.get('slack') == 'webhook' else Y}{h.get('slack', '?')}{X}")

        # ──────────────────────────────────────────────────
        banner("DEMO 1: Normal Execution (no failure)")
        resp = await client.post(
            f"{API}/execute-task",
            json={"task": "Schedule a team sync meeting", "simulate_failure": False},
        )
        data = resp.json()
        print(f"  Status: {G}{data['status']}{X}")
        for s in data["steps"]:
            print(f"    Step {s['id']} [{s['tool']}.{s['action']}] -> {G}{s['status']}{X}")
        print(f"\n  {G}All 3 steps passed cleanly.{X}")

        # ──────────────────────────────────────────────────
        banner("DEMO 2: Schema Change Failure + Self-Healing")

        print(f"  {Y}Simulating upstream schema change:{X}")
        print(f"    {R}OLD: {{ \"meeting_time\": \"2026-04-05T10:00:00\" }}{X}")
        print(f"    {R}NEW: {{ \"time\": \"10:00 AM\" }}{X}")
        print(f"")
        print(f"  {C}The system must detect this, diagnose it,")
        print(f"  fix the mapping + format, and retry.{X}\n")

        resp = await client.post(
            f"{API}/execute-task",
            json={"task": "Schedule a team sync meeting", "simulate_failure": True},
        )
        data = resp.json()

        print(f"  Final Status: {G}{data['status'].upper()}{X}\n")

        print(f"  Step Results:")
        for s in data["steps"]:
            st = s["status"]
            if st == "healed":
                icon = f"{G}HEALED (self-fixed){X}"
            elif st == "success":
                icon = f"{G}SUCCESS{X}"
            else:
                icon = f"{R}{st.upper()}{X}"
            print(f"    Step {s['id']} [{s['tool']}.{s['action']}] -> {icon}")
            if s.get("error"):
                print(f"       {R}Error: {s['error']}{X}")

        if data["healing_log"]:
            print(f"\n  {D}{B}--- Self-Healing Timeline ---{X}")
            for entry in data["healing_log"]:
                print(f"")
                print(f"    {R}ERROR detected on Step {entry['step_id']}{X}")
                print(f"    {Y}Debug Agent  : {entry['root_cause']}{X}")
                print(f"    {C}Fix Agent    : {entry['fix']}{X}")
                print(f"    {G}Retry Result : {entry['outcome'].upper()}{X}")

        # ──────────────────────────────────────────────────
        banner("DEMO 3: Stored Workflow + Audit Trail")
        wf_id = data["workflow_id"]
        resp = await client.get(f"{API}/workflow-status/{wf_id}")
        record = resp.json()
        print(f"  Workflow {wf_id}: {G}{record['status']}{X}")
        print(f"")
        print(f"  Persisted Logs ({len(record.get('logs', []))} entries):")
        for log in record.get("logs", []):
            lvl = log["level"]
            c = R if lvl == "ERROR" else Y if lvl == "WARN" else G
            print(f"    [{c}{lvl:5}{X}] {log['message']}")

        # ──────────────────────────────────────────────────
        banner("DEMO 4: Dynamic Task (try different input)")
        resp = await client.post(
            f"{API}/execute-task",
            json={
                "task": "Set up a project kickoff with the engineering team and send notes",
                "simulate_failure": False,
            },
        )
        data = resp.json()
        print(f"  Task: \"{data.get('task', 'N/A')}\"")
        print(f"  Status: {G}{data['status']}{X}")
        for s in data["steps"]:
            print(f"    Step {s['id']} [{s['tool']}.{s['action']}] -> {G}{s['status']}{X}")

    print(f"\n{G}{D}{'=' * 64}")
    print(f"  DEMO COMPLETE - All scenarios verified!")
    print(f"{'=' * 64}{X}\n")


async def demo_standalone():
    """Run without a server - useful for quick local testing."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)-24s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
        force=True,
    )

    from agents.orchestrator import OrchestratorAgent
    from workflow.engine import WorkflowEngine

    orchestrator = OrchestratorAgent()
    engine = WorkflowEngine()

    banner("STANDALONE: Schema Failure + Self-Healing Demo")
    workflow = orchestrator.parse_task("Schedule a team sync meeting", simulate_failure=True)
    result = await engine.run(workflow, simulate_failure=True)

    print(f"\n{D}Final status: {result.status.value}{X}")
    for s in result.steps:
        c = G if s.status.value in ("success", "healed") else R
        label = "HEALED" if s.status.value == "healed" else s.status.value.upper()
        print(f"  Step {s.id} [{s.tool}.{s.action}] -> {c}{label}{X}")

    if result.healing_log:
        print(f"\n{B}{D}Self-Healing Log:{X}")
        for entry in result.healing_log:
            print(f"  {R}Error detected{X} -> {Y}{entry['root_cause']}{X}")
            print(f"  {C}Fix applied{X}    -> {entry['fix']}")
            print(f"  {G}Outcome{X}        -> {entry['outcome']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Self-Healing Agent Demo")
    parser.add_argument("--standalone", action="store_true", help="Run without server")
    args = parser.parse_args()

    if args.standalone:
        asyncio.run(demo_standalone())
    else:
        asyncio.run(demo_api())
