"""Interactive command-line interface for the Hospital Ontology Agent.

Usage:
    python -m agent.cli
    python -m agent.cli --no-reasoning
    python -m agent.cli --question "Who is John Miller?"
    python -m agent.cli --show-sparql
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from .engine import OntologyAgent

BANNER = r"""
+--------------------------------------------------------------+
|          HOSPITAL MANAGEMENT ONTOLOGY AGENT                  |
|          OWL 2 + RDFLib/SPARQL + optional HermiT             |
+--------------------------------------------------------------+"""

EXAMPLES = """
Examples you can try
--------------------
  Entity lookup      Who is John Miller?
  Class query        What is a Cardiologist?
  Hierarchy          List all subclasses of Disease.
  Relationship       Who is the doctor of Robert Brown?
  Attribute          What is John Miller's blood group?
  Multi-hop          Which symptoms are caused by diseases that John Miller has?
  Transitive path    Which hospital does Dr. Patel work at?
  Inverse property   Who is the head of the Cardiology department?
  Aggregation        How many patients are there?
  Unknown facts      What is the capital of France?

Commands:  help | stats | classes | properties | reason | clear | exit
"""


def _find_java(java_home: str | None) -> str | None:
    if java_home and (Path(java_home) / "bin" / "java.exe").exists():
        return java_home
    env = os.environ.get("JAVA_HOME")
    if env and (Path(env) / "bin" / "java.exe").exists():
        return env
    if shutil.which("java"):
        return None  # already on PATH
    # Local portable JDK used during development
    fallback = Path.home() / "ontology-tools" / "jdk" / "jdk-21.0.13+9"
    if (fallback / "bin" / "java.exe").exists():
        return str(fallback)
    return None


def build_agent(args) -> OntologyAgent:
    java_home = _find_java(args.java_home) if args.reasoning else None
    agent = OntologyAgent(args.ontology, java_home=java_home, reasoning=args.reasoning)
    return agent


def print_answer(agent: OntologyAgent, answer, show_sparql: bool, show_evidence: bool) -> None:
    print()
    print("Agent: " + answer.text)
    print(f"\n[{answer.intent} | confidence {answer.confidence:.2f}]")
    if show_sparql and answer.sparql:
        print(f"SPARQL: {answer.sparql}")
    if show_evidence and answer.evidence:
        print("Evidence (ontology triples):")
        for s, p, o in answer.evidence[:6]:
            print(f"  {s}  {p}  {o}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hospital Management Ontology Agent")
    default_owl = Path(__file__).resolve().parent.parent / "ontology" / "hospital_ontology.owl"
    parser.add_argument("--ontology", default=str(default_owl), help="path to the .owl file")
    parser.add_argument("--no-reasoning", dest="reasoning", action="store_false",
                        help="disable HermiT reasoning")
    parser.add_argument("--java-home", default=None, help="path to a JDK (for HermiT)")
    parser.add_argument("--question", default=None, help="ask one question and exit")
    parser.add_argument("--show-sparql", action="store_true", help="print the SPARQL query")
    parser.add_argument("--show-evidence", action="store_true", help="print supporting triples")
    parser.set_defaults(reasoning=True)
    args = parser.parse_args(argv)

    agent = build_agent(args)
    stats = agent.onto.stats()

    if args.question:
        print_answer(agent, agent.ask(args.question), args.show_sparql, args.show_evidence)
        return 0

    print(BANNER)
    print(f"Ontology : {Path(args.ontology).name}")
    print(f"Loaded   : {stats['classes']} classes | {stats['object_properties']} object properties | "
          f"{stats['data_properties']} data properties | {stats['individuals']} individuals")
    print(f"Reasoner : {'HermiT (enabled on demand)' if args.reasoning else 'disabled'}")
    print(EXAMPLES)

    while True:
        try:
            raw = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break
        if not raw:
            continue
        cmd = raw.lower()
        if cmd in {"exit", "quit", ":q"}:
            print("Goodbye.")
            break
        if cmd in {"help", "?"}:
            print(EXAMPLES)
            continue
        if cmd == "stats":
            s = agent.onto.stats()
            print(f"\nClasses: {s['classes']} | Object properties: {s['object_properties']} | "
                  f"Data properties: {s['data_properties']} | Individuals: {s['individuals']} | "
                  f"Triples: {s['triples']}")
            print(f"Patients: {s['patients']} | Doctors: {s['doctors']} | Diseases: {s['diseases']} | "
                  f"Medications: {s['medications']} | Appointments: {s['appointments']}")
            continue
        if cmd == "classes":
            print()
            for c in agent.onto.named_classes():
                print(f"  {agent.onto.label(c)}")
            continue
        if cmd == "properties":
            print("\nObject properties:")
            for p in sorted(agent.onto.object_properties.values(), key=lambda x: x.label):
                print(f"  {p.label}")
            print("\nData properties:")
            for p in sorted(agent.onto.data_properties.values(), key=lambda x: x.label):
                print(f"  {p.label}")
            continue
        if cmd == "reason":
            if agent.reasoner is None:
                print("Reasoning is disabled. Restart without --no-reasoning.")
                continue
            ok, err = agent.reasoner.run()
            if ok:
                print("HermiT: ontology is consistent.")
                for iri in ["p001", "p003", "d004"]:
                    uri = f"http://example.org/hospital#{iri}"
                    print(f"  {iri}: inferred types = {agent.reasoner.inferred_types(uri)}")
            else:
                print(f"HermiT error: {err}")
            continue
        if cmd == "clear":
            os.system("cls" if os.name == "nt" else "clear")
            continue

        answer = agent.ask(raw)
        print_answer(agent, answer, args.show_sparql, args.show_evidence)

    return 0


if __name__ == "__main__":
    sys.exit(main())