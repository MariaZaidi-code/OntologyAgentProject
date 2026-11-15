"""Run the ontology-question demonstration and write an evidence report.

Every answer is produced live by the agent from the OWL file; expected
substrings are only used to verify the answer, never to generate it.

Usage:
    python run_demo.py
    python run_demo.py --no-reasoning
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

from agent import OntologyAgent
from agent.cli import _find_java

ROOT = Path(__file__).resolve().parent
QUESTIONS = ROOT / "tests" / "questions.json"
OUT_MD = ROOT / "docs" / "demo_results.md"
OUT_JSON = ROOT / "docs" / "demo_results.json"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser()
    parser.add_argument("--no-reasoning", dest="reasoning", action="store_false")
    parser.add_argument("--ontology", default=str(ROOT / "ontology" / "hospital_ontology.owl"))
    parser.set_defaults(reasoning=True)
    args = parser.parse_args()

    java_home = _find_java(None) if args.reasoning else None
    reasoner_label = "HermiT (owlready2)" if args.reasoning else "disabled"
    agent = OntologyAgent(args.ontology, java_home=java_home, reasoning=args.reasoning)
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))

    results = []
    passed = 0
    print("=" * 78)
    print(" HOSPITAL ONTOLOGY AGENT - DEMONSTRATION RUN")
    print(f" Ontology: {Path(args.ontology).name} | Reasoner: {reasoner_label}")
    print("=" * 78)

    for item in questions:
        t0 = time.perf_counter()
        answer = agent.ask(item["question"])
        elapsed = time.perf_counter() - t0

        text_l = answer.text.lower()
        missing = [e for e in item.get("expect", []) if e.lower() not in text_l]
        forbidden = [f for f in item.get("forbid", []) if f.lower() in text_l]
        is_unknown = item["category"] == "unknown"
        ok = not missing and not forbidden and ((not answer.ok) if is_unknown else answer.ok)
        passed += int(ok)

        results.append({
            "id": item["id"],
            "category": item["category"],
            "question": item["question"],
            "answer": answer.text,
            "intent": answer.intent,
            "confidence": answer.confidence,
            "ok": ok,
            "expected_facts": item.get("expect", []),
            "missing": missing,
            "forbidden_matches": forbidden,
            "evidence": [f"{s} {p} {o}" for s, p, o in answer.evidence[:6]],
            "sparql": answer.sparql,
            "seconds": round(elapsed, 3),
        })

        status = "PASS" if ok else "FAIL"
        print(f"\n[{status}] Q{item['id']:02d} ({item['category']}): {item['question']}")
        one_line = " ".join(answer.text.split())
        print("  -> " + (one_line[:300] + ("..." if len(one_line) > 300 else "")))
        if missing:
            print("  missing expected facts: " + ", ".join(missing))
        if forbidden:
            print("  forbidden text found: " + ", ".join(forbidden))

    total = len(results)
    print("\n" + "=" * 78)
    print(f" RESULT: {passed}/{total} checks passed ({passed / total * 100:.1f}%)")
    print("=" * 78)

    # ------------------------------------------------------------- markdown
    lines = [
        "# Agent Demonstration - Executed Results",
        "",
        f"- **Run:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- **Ontology file:** `{Path(args.ontology).name}`",
        f"- **Reasoner:** {reasoner_label}",
        f"- **Result:** {passed}/{total} checks passed",
        "",
        "Each answer below was generated at runtime by querying the OWL graph. "
        "The *expected facts* column lists the facts that the automated check looked for; "
        "they were not supplied to the agent.",
        "",
        "| # | Category | Question | Result |",
        "|---|----------|----------|--------|",
    ]
    for r in results:
        lines.append(f"| {r['id']} | {r['category']} | {r['question']} | {'PASS' if r['ok'] else 'FAIL'} |")

    lines += ["", "## Detailed question / answer log", ""]
    for r in results:
        lines.append(f"### Q{r['id']}. {r['question']}")
        lines.append("")
        lines.append(f"- **Category:** {r['category']}")
        lines.append(f"- **Intent detected:** `{r['intent']}` (confidence {r['confidence']:.2f})")
        lines.append(f"- **Status:** {'PASS' if r['ok'] else 'FAIL'} ({r['seconds']} s)")
        if r["expected_facts"]:
            lines.append("- **Expected facts:** " + ", ".join(r["expected_facts"]))
        lines.append("")
        lines.append("**Agent answer:**")
        lines.append("")
        lines.append("> " + r["answer"].replace("\n", "\n> "))
        if r["sparql"]:
            lines.append("")
            lines.append("**SPARQL used:**")
            lines.append("")
            lines.append("```sparql")
            lines.append(r["sparql"])
            lines.append("```")
        if r["evidence"]:
            lines.append("")
            lines.append("**Evidence triples (first 6):**")
            lines.append("")
            lines.append("```")
            lines.extend(r["evidence"])
            lines.append("```")
        lines.append("")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {OUT_MD.relative_to(ROOT)} and {OUT_JSON.relative_to(ROOT)}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())