# Architecture Report – Hospital Management Ontology Agent

## 1. Domain and ontology design

The domain is **hospital management**. The ontology is authored in Turtle
(`ontology/hospital_ontology.ttl`) and serialised to RDF/XML
(`ontology/hospital_ontology.owl`) for Protégé and for the agent.

### 1.1 Classes

Base classes: `Hospital`, `Department`, `Ward`, `Doctor` (with subclasses
`Cardiologist`, `Neurologist`, `Surgeon`, `GeneralPractitioner`,
`Pulmonologist`), `Nurse`, `Patient`, `Disease` (with subclasses
`ChronicDisease`, `AcuteDisease`, `CardiovascularDisease`, `RespiratoryDisease`,
`NeurologicalDisease`, `EndocrineDisease`, `InfectiousDisease`, `Diabetes`,
`Hypertension`, …), `Medication`, `Symptom`, `Appointment`,
`InsurancePlan`, `MedicalRecord`, `BodySystem`.

Defined (inferred) classes, each an `owl:equivalentClass` of an intersection:

- `ChronicDiseasePatient` – `Patient` ∩ `diagnosedWith some ChronicDisease`
- `DiabetesPatient` – `Patient` ∩ `diagnosedWith some Diabetes`
- `CardiovascularPatient` – `Patient` ∩ `diagnosedWith some CardiovascularDisease`
- `PatientWithComorbidities` – `Patient` ∩ `diagnosedWith min 2 Disease`
- `CardiologyPatient` – `Patient` ∩ `hasAppointment some (Appointment ∩ withDoctor some Cardiologist)`
- `SeniorPatient` – `Patient` ∩ `age some (xsd:integer with minInclusive 65)`
- `DepartmentHead` – `Doctor` ∩ `headOf some Department`
- `BusyDoctor` – `Doctor` ∩ `hasScheduledAppointment min 2 Appointment`

Explicit `rdfs:subClassOf` links were added so that subclass queries work both
through the asserted hierarchy and through the reasoner.

### 1.2 Properties

- **Object properties (28):** `treatedBy`/`treatsPatient` (inverse pair),
  `partOf` (transitive), `interactsWith` (symmetric + irreflexive),
  `worksIn`, `headOf`, `affiliatedWith`, `diagnosedWith`, `hasSymptom`,
  `causes`, `hasAffectedSystem`, `treatsDisease`, `hasAppointment`,
  `forPatient`, `withDoctor`, `hasScheduledAppointment`, `hasMedicalRecord`,
  `recordsDiagnosis`, `hasPrescription`, `prescribedFor`, `prescribedBy`,
  `allergicTo`, `hasInsurance`, `coversDisease`, `hasPart`, `indicatedBy`,
  `affectsPatient`, …
- **Data properties (27):** `patientId`, `doctorId`, `employeeId`,
  `policyNumber`, `age`, `birthDate`, `gender`, `bloodGroup`, `phone`,
  `email`, `name`, `specialty`, `licenseNumber`, `diseaseCode`, `icdCode`,
  `severity`, `chronic`, `contagious`, `dosage`, `frequency`, `cost`,
  `reason`, `status`, `appointmentDate`, `appointmentTime`, `roomNumber`,
  `recordDate`.

Domains and ranges are declared for almost all properties; the few inverse
properties (`treatsPatient`, `partOf`, …) intentionally keep an open domain so
that they can be used in both directions.

### 1.3 Individuals

127 named individuals: 12 patients, 10 doctors, 14 diseases, 17 medications,
13 appointments, 4 hospitals, 6 departments, 6 wards, 4 insurance plans,
4 medical records, 12 symptoms, 5 body systems. `owl:AllDifferent` axioms
cover patients and medications; without them the reasoner cannot infer the
`minQualifiedCardinality` classes (no Unique Name Assumption in OWL).

### 1.4 OWL 2 features used

- `rdfs:subClassOf`, `owl:equivalentClass`, `owl:intersectionOf`
- `owl:Restriction` with `owl:someValuesFrom`, `owl:minQualifiedCardinality`,
  `owl:onClass`, `owl:onDatatype`, `owl:withRestrictions` (`xsd:minInclusive`)
- `owl:inverseOf`, `owl:TransitiveProperty`, `owl:SymmetricProperty`,
  `owl:IrreflexiveProperty`, `owl:FunctionalProperty`
- `owl:AllDifferent`, `owl:members`
- `rdfs:domain`, `rdfs:range`, `rdfs:label`, `rdfs:comment`
- `xsd:dateTime`, `xsd:integer`, `xsd:nonNegativeInteger`, `xsd:decimal`,
  `xsd:string`, `xsd:boolean`

`xsd:date` was replaced by `xsd:dateTime` because HermiT (as bundled with
owlready2 0.51) rejects `xsd:date`.

## 2. Agent architecture

```
┌──────────────┐      ┌──────────────────────┐
│  CLI / UI    │  →   │  OntologyAgent       │  →  natural language answer
└──────────────┘      │  (intent router +    │
                      │   ~35 handlers)      │
                      └────────┬─────────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
       ┌────────────┐   ┌────────────┐   ┌──────────────┐
       │OntologySvc │   │ReasonerSvc │   │ rdflib Graph │
       │ aliases,   │   │ HermiT     │   │ SPARQL       │
       │ BFS, stats │   │ (owlready) │   │ (rdflib)     │
       └────────────┘   └────────────┘   └──────────────┘
```

### 2.1 OntologyService (`agent/ontology.py`)

- Loads the OWL file into an `rdflib.Graph` (RDF/XML or Turtle).
- Builds typed indexes: `classes`, `object_properties`, `data_properties`,
  `individuals`.
- Builds a **normalised alias index** for entity linking (labels, humanised
  local names, doctor surnames, identifiers such as `P-1001`).
- Exposes `select()` (SPARQL), `label()`, `local()`, `objects()`,
  `subjects()`, `values()`, `instances_of()`, `is_subclass()`,
  `direct/all_subclasses`, `count_instances()`.
- `find_paths()` – BFS over object-property edges (forward and inverse,
  tracking reversed edges) with optional preferred predicates and a
  depth limit; returns `PathResult` objects whose `describe()` renders
  `John Miller -> [treated by] Dr. Alice Chen`.
- `stats()` – triple/class/property/individual counts and instance counts.

### 2.2 ReasonerService (`agent/ontology.py`)

Wraps owlready2 + HermiT. Uses a bare filename plus `onto_path` (file URIs
break on Windows). `sync_reasoner_hermit(..., infer_property_values=True)`.
Caches the first run; reports consistency and inferred types per individual.

### 2.3 OntologyAgent (`agent/engine.py`)

1. Normalises the question.
2. Links entities (`match_entities`).
3. Classifies into one of ~35 intents using keyword + entity-type heuristics.
4. Runs the matching handler, which executes SPARQL / graph queries and builds
   an `Answer` (text, intent, confidence, SPARQL, evidence triples, ok flag).
5. Falls back to “I could not find an answer …” when no handler matches or
   the graph returns nothing.

Handlers cover: entity description, class description, subclass/superclass,
instances, relationships (generic + specialised), attributes, multi-hop
(symptoms, hospital of doctor, doctors in department/hospital, insurance
coverage, medication interactions, comorbidity, …), counts, superlatives,
relationship paths, schema listing, reasoning queries.

### 2.4 Multi-hop logic

- **Symptoms of a patient:** patient → `diagnosedWith` → disease → `causes` →
  symptom.
- **Hospital of a doctor:** doctor → `worksIn` → department → `partOf+` →
  hospital (transitive SPARQL property path).
- **Insurance coverage:** patient → `hasInsurance` → plan; patient →
  `diagnosedWith` → disease; plan → `coversDisease` → disease; intersect.
- **Medication interactions:** patient → `treatedWith`/`hasPrescription` →
  medication → `interactsWith` → medication (symmetric).
- **Relationship path:** BFS over all object-property edges up to depth 3,
  preferring predicates whose labels share tokens with the question; renders
  each edge with its inverse label when traversed backwards.
- **Reasoning:** HermiT classifies individuals into the defined classes; the
  agent reports them as “inferred by the HermiT reasoner”.

## 3. SPARQL grounding

Every answer is accompanied by the SPARQL query that produced it (printed by
the CLI with `--show-sparql` and shown in the Streamlit “SPARQL query used”
expander). Examples:

```sparql
-- Doctor of a patient
SELECT ?d WHERE { h:p003 h:treatedBy ?d }

-- Transitive hospital
SELECT ?h WHERE { h:d002 h:worksIn/h:partOf+ ?h . ?h a h:Hospital }

-- Senior patients (reasoner-inferred, queried via owlready2)
-- (reported as instances of h:SeniorPatient after HermiT)
```

No answer string is ever taken from a template that ignores the graph: handlers
call `service.objects/subjects/values/select` and format the returned URIs and
literals. Mutating the graph changes the answer (covered by
`test_answers_are_grounded_in_the_graph`).

## 4. Test results

- **Ontology tests (`tests/test_ontology.py`):** 18 tests – parsing, class
  hierarchy, property domains/ranges/characteristics, individual counts,
  values, restrictions, `AllDifferent`, SPARQL endpoint, medical records,
  HermiT consistency and inference, transitive `partOf`.
- **Agent tests (`tests/test_agent.py`):** 43 tests – the full 38-question
  suite (parametrised), unknown-fact refusal, entity linking, intent routing,
  graph-grounded answers, SPARQL/evidence exposure, reasoning, superlatives.
- **Demo run (`run_demo.py`):** 38/38 checks pass (100.0 %). Output:
  `docs/demo_results.md`, `docs/demo_results.json`.
- **Full pytest run:** 61 tests pass in ~16 s.

## 5. Environment

- Python 3.11.9, rdflib 7.6.0, owlready2 0.51, streamlit 1.66.1, pytest 9.0.3
- JDK 21.0.13 (Temurin) for HermiT and Protégé
- Protégé 5.6.9
- OS: Windows 11

## 6. Known limitations and future work

- The agent is rule/intent based, not an LLM. It covers the documented
  question categories but will not paraphrase arbitrary phrasings.
- OWL’s Open-World Assumption means “how many” answers reflect *asserted*
  instances; missing individuals are not treated as zero.
- Cardinality inference needs `owl:AllDifferent`; it is included for patients
  and medications but not for every class.
- Pellet (bundled with owlready2) does not run on Java 21; HermiT is used
  instead.
