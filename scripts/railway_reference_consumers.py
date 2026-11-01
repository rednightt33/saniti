#!/usr/bin/env python3
"""M308: list, and on request redeploy, the services that read a variable of another service by reference.

Railway resolves `${{service.NAME}}` when a service is deployed. A secret replaced at its source therefore stays old
in every service that references it until that service is deployed again (2026-10-30: market-web-governor kept the
OpenRouter key of its 2026-10-18 deploy and every web search was refused). The consumers are read from the live
project (each service's unrendered variables), never from a list kept in this repository, so a new consumer is found
without a code change.

Usage (repository root; RAILWAY_API_TOKEN in the environment; prints names and references only, never a value):
    python3 scripts/railway_reference_consumers.py market-ai-orc.OPENROUTER_API_KEY
    python3 scripts/railway_reference_consumers.py telegram-monitor.TELEGRAM_NOTIFY_SECRET --redeploy
    python3 scripts/railway_reference_consumers.py --all            # every cross-service reference
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request

PROJECT = "8aef1702-030b-49cb-9df7-5ac2e0a42691"  # PROJECT_CONTEXT.md
DEV = "4d3e5af2-302b-4a2e-84e2-7d7476d6ff49"
API = "https://backboard.railway.com/graphql/v2"
REFERENCE = re.compile(r"\$\{\{\s*([A-Za-z0-9_.-]+)\.([A-Za-z0-9_]+)\s*\}\}")


def graphql(query: str, variables: dict) -> dict:
    token = os.environ.get("RAILWAY_API_TOKEN")
    if not token:
        sys.exit("RAILWAY_API_TOKEN is not set")
    request = urllib.request.Request(API, data=json.dumps({"query": query, "variables": variables}).encode(),
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                                              "User-Agent": "saniti-reference-consumers"})
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.load(response)
    if body.get("errors"):
        sys.exit(f"Railway API: {body['errors'][0].get('message')}")
    return body["data"]


def services(project: str) -> list[dict]:
    data = graphql("query($p:String!){ project(id:$p){ services{ edges{ node{ id name } } } } }", {"p": project})
    return [edge["node"] for edge in data["project"]["services"]["edges"]]


def references(project: str, environment: str, service_id: str) -> dict[str, tuple[str, str]]:
    """{variable: (source service, source variable)} for every variable that is only a reference to another
    service. Values are read unrendered and kept only when they are a reference; nothing else leaves this function."""
    data = graphql("query($p:String!,$e:String!,$s:String!){ variables(projectId:$p, environmentId:$e, "
                   "serviceId:$s, unrendered:true) }", {"p": project, "e": environment, "s": service_id})
    out = {}
    for name, value in (data.get("variables") or {}).items():
        match = REFERENCE.fullmatch(value.strip()) if isinstance(value, str) else None
        if match and match.group(1) not in ("shared", "RAILWAY"):
            out[name] = (match.group(1), match.group(2))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", nargs="?", help="service.VARIABLE whose consumers are wanted")
    parser.add_argument("--all", action="store_true", help="list every cross-service reference")
    parser.add_argument("--redeploy", action="store_true", help="redeploy each consumer of SOURCE (Railway CLI)")
    parser.add_argument("--project", default=PROJECT)
    parser.add_argument("--environment", default=DEV)
    args = parser.parse_args()
    if not args.all and not args.source:
        parser.error("give service.VARIABLE or --all")
    wanted = tuple(args.source.split(".", 1)) if args.source else None
    if wanted and len(wanted) != 2:
        parser.error("SOURCE is service.VARIABLE")
    consumers = []
    for service in services(args.project):
        for name, source in sorted(references(args.project, args.environment, service["id"]).items()):
            if wanted is None or source == wanted:
                consumers.append((service["name"], name, f"{source[0]}.{source[1]}"))
    for service, name, source in consumers:
        print(f"{service}\t{name}\t<- ${{{{{source}}}}}")
    if not consumers:
        print("no service references it")
    if args.redeploy and wanted:
        for service in sorted({c[0] for c in consumers}):
            print(f"redeploy {service}")
            subprocess.run(["railway", "redeploy", "-p", args.project, "-e", args.environment, "-s", service, "-y"],
                           check=True)
        print("claim each one only once its new deployment reaches SUCCESS (AGENTS, History rules)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
