"""End-to-end tests for the question-answering agent."""
from __future__ import annotations

import pytest
from rdflib import Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from agent import H, OntologyAgent


def _load_questions():
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parent / "questions.json"
    return json.loads(path.read_text(encoding="utf-8"))


QUESTIONS = _load_questions()


@pytest.mark.parametrize("item", QUESTIONS, ids=[f"Q{q['id']}-{q['category']}" for q in QUESTIONS])
def test_question_suite(agent, item):
    """Every documented question must be answered correctly and honestly."""
    answer = agent.ask(item["question"])
    text = answer.text.lower()

    missing = [fact for fact in item.get("expect", []) if fact.lower() not in text]
    forbidden = [fact for fact in item.get("forbid", []) if fact.lower() in text]
    assert not missing, f"missing facts {missing} in:\n{answer.text}"
    assert not forbidden, f"forbidden facts {forbidden} in:\n{answer.text}"

    if item["category"] == "unknown":
        assert answer.ok is False
        assert "could not find an answer" in text
    else:
        assert answer.ok is True
        assert answer.intent != "fallback"


def test_unknown_question_is_refused(agent):
    answer = agent.ask("Who won the 1998 FIFA World Cup?")
    assert answer.ok is False
    assert "could not find an answer" in answer.text.lower()
    assert "France" not in answer.text and "Zidane" not in answer.text


def test_entity_linking(agent):
    matches = agent.onto.match_entities("Who is the doctor of John Miller?")
    labels = {agent.onto.label(m.uri) for m in matches}
    assert "John Miller" in labels
    assert any("doctor" in label.lower() for label in labels)


def test_intents_are_routed(agent):
    cases = {
        "Who is John Miller?": "individual_description",
        "What is a Cardiologist?": "class_description",
        "Who is the doctor of Robert Brown?": "generic_relation",
        "What is John Miller's blood group?": "attribute",
        "Which symptoms are caused by diseases that John Miller has?": "symptoms_from_patient_diseases",
        "Which hospital does Dr. Patel work at?": "hospital_of_doctor",
        "How many patients are there?": "count_instances",
        "Who is the oldest patient?": "superlative",
    }
    for question, expected in cases.items():
        answer = agent.ask(question)
        assert answer.intent == expected, f"{question!r} -> {answer.intent}"


def test_answers_are_grounded_in_the_graph(owl_path):
    """Mutating the graph must change the answer: nothing is hardcoded."""
    local = OntologyAgent(str(owl_path), reasoning=False)
    before = local.ask("How many patients are there?").text

    node = URIRef(str(H) + "p_test")
    graph = local.onto.graph
    graph.add((node, RDF.type, OWL.NamedIndividual))
    graph.add((node, RDF.type, H.Patient))
    graph.add((node, RDFS.label, Literal("Test Patient", lang="en")))
    graph.add((node, H.patientId, Literal("P-9999")))
    graph.add((node, H.age, Literal(41)))
    try:
        after = local.ask("How many patients are there?").text
        assert before != after
        assert "13" in after
        assert "Test Patient" not in before
    finally:
        graph.remove((node, None, None))


def test_sparql_trace_is_exposed(agent):
    answer = agent.ask("Who is the doctor of Robert Brown?")
    assert answer.ok
    assert answer.sparql and "SELECT" in answer.sparql
    assert answer.evidence
    assert answer.confidence >= 0.5


def test_reasoner_inferred_answer(agent):
    answer = agent.ask("Which patients are senior patients?")
    assert answer.ok
    assert "inferred" in answer.text.lower()
    assert "John Miller" in answer.text


def test_superlative_uses_data_property(agent):
    answer = agent.ask("Who is the oldest patient?")
    assert "William Thomas" in answer.text
    assert "80" in answer.text
