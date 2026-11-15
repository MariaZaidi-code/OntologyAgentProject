"""Shared pytest fixtures.

The ontology and the agent are loaded once per test session: parsing the
~1,750-triple OWL file and starting the HermiT JVM are both relatively
expensive operations.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent import OntologyAgent, OntologyService
from agent.cli import _find_java

ROOT = Path(__file__).resolve().parent.parent
OWL = ROOT / "ontology" / "hospital_ontology.owl"
QUESTIONS = ROOT / "tests" / "questions.json"


@pytest.fixture(scope="session")
def owl_path() -> Path:
    assert OWL.exists(), f"missing ontology file: {OWL}"
    return OWL


@pytest.fixture(scope="session")
def service(owl_path: Path) -> OntologyService:
    return OntologyService(owl_path)


@pytest.fixture(scope="session")
def agent(owl_path: Path) -> OntologyAgent:
    return OntologyAgent(str(owl_path), java_home=_find_java(None), reasoning=True)


@pytest.fixture(scope="session")
def questions() -> list[dict]:
    return json.loads(QUESTIONS.read_text(encoding="utf-8"))
