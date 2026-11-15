# Hospital Management Ontology Agent

A university project **Knowledge Representation & Ontologies (OWL 2)** deliverable from Maria Zaidi (`mariazaidi-code`).

Two deliverables, shipped in one repository:

1. **`ontology/hospital_ontology.owl`** — an OWL 2 ontology for the hospital domain, developed in Protégé 5.6.9 and reasoner-checked with HermiT (consistent).
2. **`agent/`** — a Python AI agent that answers natural-language questions by querying the OWL file through RDFLib + SPARQL. No answer is hard-coded: every fact is read from the ontology at question time.

## Project layout

```text
OntologyAgentProject/
├── ontology/
│   ├── hospital_ontology.ttl          # readable Turtle source
│   └── hospital_ontology.owl          # RDF/XML deliverable (Protégé / agent)
├── agent/
│   ├── ontology.py                    # OntologyService + ReasonerService
│   ├── engine.py                      # OntologyAgent (intent routing + handlers)
│   ├── cli.py                         # interactive terminal UI
│   └── app.py                         # Streamlit chat UI
├── tests/
│   ├── conftest.py                    # shared fixtures
│   ├── test_ontology.py               # structural + logical ontology tests
│   ├── test_agent.py                  # end-to-end agent tests
│   └── questions.json                 # 38 test questions with expected facts
├── docs/
│   ├── demo_results.md                # executed 38/38 question log
│   └── REPORT.md                      # architecture report
├── screenshots/                        # genuine Protégé / CLI / agent captures
├── run_demo.py                        # executes the 38-question demo
├── requirements.txt
└── README.md
```

## Ontology summary

- **Classes:** 52 named classes (base: `Hospital`, `Department`, `Ward`, `Doctor`, `Nurse`, `Patient`, `Disease`, `ChronicDisease`, `Medication`, `Symptom`, `Appointment`, `InsurancePlan`, `MedicalRecord`, `BodySystem`, …).
- **Defined (inferred) classes:** `DiabetesPatient`, `CardiovascularPatient`, `ChronicDiseasePatient`, `PatientWithComorbidities`, `CardiologyPatient`, `SeniorPatient`, `DepartmentHead`, `BusyDoctor`.
- **Object properties:** 28 (e.g. `treatedBy` / `treatsPatient` inverse, `partOf` transitive, `interactsWith` symmetric + irreflexive, `affiliatedWith`, `diagnosedWith`, …).
- **Data properties:** 27 (e.g. `age`, `bloodGroup`, `dosage`, `licenseNumber`, `cost`, `frequency`, `severity`, …).
- **Individuals:** 127 (12 patients, 10 doctors, 14 diseases, 17 medications, 13 appointments, wards, departments, hospitals, …).
- **Restrictions:** `someValuesFrom`, `minQualifiedCardinality` (>= 2 diseases / >= 2 scheduled appointments), OWL 2 datatype restriction (`age >= 65`), nested restrictions (cardiology appointments).
- **Axioms:** `owl:AllDifferent` on patients and medications (required for cardinality inference under the Open-World Assumption), domains and ranges, disjointness.

## Agent capabilities

- **Entity lookup** — “Who is John Miller?”
- **Class description** — “What is a Cardiologist?”
- **Class hierarchy** — “List all subclasses of Doctor.”
- **Class instances** — “List all chronic diseases.”
- **Relationships** — “Who is the doctor of Robert Brown?”
- **Attributes** — “What is John Miller’s blood group?”, “What is the dosage of Metformin?”
- **Multi-hop** — “Which symptoms are caused by diseases that John Miller has?”
- **Transitive paths** — “Which hospital does Dr. Patel work at?”
- **Inverse properties** — “Who is the head of the Cardiology department?”
- **Symmetric properties** — “Which medications interact with Aspirin?”
- **Aggregation** — “How many patients are there?”, “How many appointments does Dr. Michael Smith have?”
- **Superlatives** — “Who is the oldest patient?”
- **Reasoning** — “Which patients are senior patients?” (HermiT-inferred)
- **Relationship paths** — “What is the relationship between John Miller and Dr. Alice Chen?” (BFS over object properties)
- **Unknown facts** — honestly refused (“I could not find an answer …”)

## Demonstration result

```
python run_demo.py
```

38/38 checks passed. The executed log is in `docs/demo_results.md`, and the structured evidence dump is in `docs/demo_results.json`.

Highlights from the demo log:

- **Entity lookup:** `Who is John Miller?` → Patient P-1001, diagnoses Type 2 Diabetes + Hypertension, blood group O+, treated by Dr. Alice Chen.
- **Multi-hop:** `Which symptoms are caused by diseases that John Miller has?` → Excessive Thirst, Frequent Urination, Headache, Blurred Vision.
- **Transitive path:** `Which hospital does Dr. Patel work at?` → Cardiology, part of St. Mary’s Hospital.
- **Inverse property:** `Who is the head of the Cardiology department?` → Dr. Rajesh Patel.
- **Symmetric property:** `Which medications interact with Aspirin?` → Warfarin.
- **Reasoning:** `Which patients are senior patients?` → Robert Brown, John Miller, William Thomas (HermiT-inferred).
- **Unknown facts:** `What is the capital of France?` → “I could not find an answer …” (refused, no Paris).

Full question-by-question answers with SPARQL and evidence triples are in `docs/demo_results.md`.

## Setup

### 1. Python dependencies

```bash
cd C:\Users\Go\OntologyAgentProject
pip install -r requirements.txt
```

### 2. Java (only needed for HermiT reasoning and Protégé)

Download a JDK (Temurin 21 was used) and either set `JAVA_HOME` or pass `--java-home` to the CLI. Protégé 5.6.9 is only needed to view the ontology.

## Running

### Command line

```bash
# interactive
$env:PYTHONIOENCODING='utf-8'
python -m agent.cli

# single question
python -m agent.cli --question "Who is John Miller?" --show-sparql
```

### Streamlit UI

```bash
streamlit run agent/app.py
```

### Demo / evidence run

```bash
$env:PYTHONIOENCODING='utf-8'
python run_demo.py
```

Writes `docs/demo_results.md` and `docs/demo_results.json` (38/38 checks pass).

### Tests

```bash
python -m pytest -q
```

61 tests pass (ontology + agent).

## Protégé

Open `ontology/hospital_ontology.owl` in Protégé 5.6.9, then:

- `Reasoner` → `HermiT 1.4.3.456` → `Start reasoner` (reasoner must report *consistent*).
- Inspect the class hierarchy, object/data properties, individuals and the DL Query tab (`SeniorPatient` → 3 inferred individuals).

Screenshots of all of the above are in `screenshots/`.

## Honest limitations

- The agent only answers facts present in the OWL file. Questions outside the domain are refused rather than answered from general knowledge.
- OWL has no Unique Name Assumption, so `owl:AllDifferent` axioms are required for cardinality inference; they are included.
- `xsd:date` was replaced by `xsd:dateTime` because HermiT (as bundled with owlready2) rejects `xsd:date`.

## Author

- Maria Zaidi — `mariazaidi-code`
