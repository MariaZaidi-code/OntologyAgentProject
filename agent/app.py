"""Streamlit chat interface for the Hospital Management Ontology agent.

Run with:
    streamlit run agent/app.py

The UI is only a thin layer over :class:`agent.engine.OntologyAgent`; every
answer is produced by querying the OWL file, exactly as in the CLI.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st
from rdflib import URIRef

from agent.cli import _find_java
from agent.engine import OntologyAgent

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OWL = ROOT / "ontology" / "hospital_ontology.owl"

SAMPLES = [
    "Who is John Miller?",
    "What is a Cardiologist?",
    "Which diseases does Dr. Patel treat?",
    "Which symptoms are caused by diseases that John Miller has?",
    "Which hospital does Dr. Patel work at?",
    "Which doctors work in departments that are part of City General Hospital?",
    "Which patients are senior patients?",
    "Who is the head of the Cardiology department?",
    "What is the relationship between John Miller and Dr. Alice Chen?",
    "How many patients have diabetes?",
    "Who is the oldest patient?",
    "What is the capital of France?",
]

st.set_page_config(
    page_title="Hospital Ontology Agent",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource(show_spinner="Loading hospital_ontology.owl ...")
def load_agent(owl_path: str, reasoning: bool) -> OntologyAgent:
    java_home = _find_java(None) if reasoning else None
    return OntologyAgent(owl_path, java_home=java_home, reasoning=reasoning)


def render_answer(answer) -> None:
    st.markdown(answer.text)
    st.caption(f"intent: `{answer.intent}` · confidence: {answer.confidence:.2f}")
    if answer.sparql:
        with st.expander("SPARQL query used"):
            st.code(answer.sparql, language="sparql")
    if answer.evidence:
        with st.expander(f"Supporting ontology triples ({len(answer.evidence)})"):
            for subject, predicate, obj in answer.evidence[:12]:
                st.code(f"{subject} {predicate} {obj}", language="turtle")


# --------------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("🏥 Ontology Agent")
    st.caption("OWL 2 + RDFLib/SPARQL + HermiT")

    owl_path = st.text_input("Ontology file", value=str(DEFAULT_OWL))
    use_reasoner = st.toggle("Enable HermiT reasoning", value=True)

    try:
        agent = load_agent(owl_path, use_reasoner)
    except Exception as exc:  # pragma: no cover - shown to the user
        st.error(f"Could not load the ontology: {exc}")
        st.stop()

    stats = agent.onto.stats()
    st.subheader("Ontology statistics")
    col_a, col_b = st.columns(2)
    col_a.metric("Classes", stats["classes"])
    col_b.metric("Individuals", stats["individuals"])
    col_a.metric("Object properties", stats["object_properties"])
    col_b.metric("Data properties", stats["data_properties"])
    st.metric("Triples", stats["triples"])

    with st.expander("Instance counts"):
        st.write(
            {
                "Patients": stats["patients"],
                "Doctors": stats["doctors"],
                "Diseases": stats["diseases"],
                "Medications": stats["medications"],
                "Appointments": stats["appointments"],
            }
        )

    if use_reasoner:
        if st.button("Run HermiT and show inferences", use_container_width=True):
            if agent.reasoner is None:
                st.warning("Reasoner not initialised.")
            else:
                with st.spinner("Running HermiT ..."):
                    ok, error = agent.reasoner.run()
                if ok:
                    st.success("Ontology is consistent.")
                    rows = []
                    for iri in ("p001", "p003", "d004"):
                        uri = f"http://example.org/hospital#{iri}"
                        types = agent.reasoner.inferred_types(uri)
                        rows.append({
                            "individual": agent.onto.label(URIRef(uri)),
                            "inferred types": ", ".join(t for t in types if t != "NamedIndividual"),
                        })
                    st.dataframe(rows, use_container_width=True, hide_index=True)
                else:
                    st.error(f"Reasoner error: {error}")

    with st.expander("Browse classes"):
        st.write(sorted(agent.onto.label(c) for c in agent.onto.named_classes()))

    with st.expander("Sample questions"):
        for sample in SAMPLES:
            st.markdown(f"- {sample}")

    st.divider()
    st.caption(
        "Answers are computed from the OWL graph at question time. "
        "When a fact is absent the agent says so instead of guessing."
    )

# ------------------------------------------------------------------------ main
st.title("Hospital Management Ontology — Question Answering")
st.write(
    "Ask about patients, doctors, diseases, medications, departments, wards, "
    "appointments and insurance plans. The agent links your question to OWL "
    "entities, maps it to a SPARQL/graph query, and answers only from the ontology."
)

if "messages" not in st.session_state:
    st.session_state.messages = []

if not st.session_state.messages:
    st.info(
        "Try one of the examples below, or type a question. "
        "Unknown facts are refused rather than invented."
    )
    cols = st.columns(2)
    for index, sample in enumerate(SAMPLES[:6]):
        if cols[index % 2].button(sample, key=f"sample_{index}", use_container_width=True):
            st.session_state.pending = sample
            st.rerun()

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if message["role"] == "user":
            st.markdown(message["text"])
        else:
            render_answer(message["answer"])

prompt = st.chat_input("Ask a question about the hospital ontology ...")
if "pending" in st.session_state and st.session_state.pending:
    prompt = st.session_state.pop("pending")

if prompt:
    st.session_state.messages.append({"role": "user", "text": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Querying the ontology ..."):
            answer = agent.ask(prompt)
        render_answer(answer)
        if not answer.ok:
            st.warning(
                "This fact is not present in hospital_ontology.owl. "
                "The agent does not guess or use outside knowledge."
            )
    st.session_state.messages.append({"role": "assistant", "answer": answer})

st.divider()
st.caption(
    "Deliverable for the Knowledge Representation & Ontologies project · "
    "Protégé 5.6.9 · OWL 2 · rdflib 7.6 · owlready2/HermiT"
)
