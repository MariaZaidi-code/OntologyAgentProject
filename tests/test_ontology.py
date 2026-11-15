"""Structural and logical tests for the hospital OWL 2 ontology."""
from __future__ import annotations

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

from agent import H


def _has_type(graph: Graph, subject: URIRef, cls: URIRef) -> bool:
    return (subject, RDF.type, cls) in graph


def test_ontology_parses_as_rdf_xml(owl_path):
    graph = Graph()
    graph.parse(str(owl_path), format="xml")
    assert len(graph) > 1000, "ontology should contain a rich set of triples"


def test_namespace_and_ontology_header(service):
    graph = service.graph
    assert (URIRef(str(H)[:-1]), RDF.type, OWL.Ontology) in graph
    assert len(list(graph.objects(None, RDFS.label))) > 100


def test_required_classes_exist(service):
    expected = {
        "Hospital", "Department", "Ward", "Doctor", "Nurse", "Patient",
        "Disease", "ChronicDisease", "Medication", "Symptom", "Appointment",
        "InsurancePlan", "MedicalRecord", "BodySystem",
    }
    labels = {service.label(c) for c in service.classes}
    missing = {e for e in expected if e not in {c.replace(" ", "") for c in labels}}
    # Compare on the compact class-name form as well as the label form.
    names = {str(c).split("#")[-1] for c in service.classes}
    missing = {e for e in expected if e not in names and e not in labels}
    assert not missing, f"missing classes: {sorted(missing)}"


def test_defined_owl2_classes_exist(service):
    expected = {
        "DiabetesPatient", "CardiovascularPatient", "ChronicDiseasePatient",
        "PatientWithComorbidities", "CardiologyPatient", "SeniorPatient",
        "DepartmentHead", "BusyDoctor",
    }
    names = {str(c).split("#")[-1] for c in service.classes}
    assert expected <= names


def test_class_hierarchy_is_populated(service):
    assert len(service.direct_subclasses(H.Doctor)) >= 4
    assert len(service.direct_subclasses(H.Disease)) >= 3
    assert service.is_subclass(H.Cardiologist, H.Doctor)
    assert service.is_subclass(H.Diabetes, H.ChronicDisease)
    assert service.is_subclass(H.Diabetes, H.Disease)
    assert not service.is_subclass(H.Doctor, H.Patient)


def test_object_properties_have_domain_and_range(service):
    assert len(service.object_properties) >= 20
    complete = [i for i in service.object_properties.values() if i.domain and i.range]
    assert len(complete) >= 20, "most object properties should declare domain and range"
    for uri in (H.diagnosedWith, H.worksIn, H.treatedBy, H.headOf,
                H.coversDisease, H.allergicTo, H.interactsWith):
        info = service.object_properties[uri]
        assert info.domain, f"{info.label} lacks rdfs:domain"
        assert info.range, f"{info.label} lacks rdfs:range"


def test_data_properties_have_domain_and_range(service):
    assert len(service.data_properties) >= 20
    for uri in (H.age, H.bloodGroup, H.dosage, H.licenseNumber):
        info = service.data_properties[uri]
        assert info.domain, f"{info.label} lacks rdfs:domain"
        assert info.range, f"{info.label} lacks rdfs:range"


def test_property_characteristics(service):
    assert service.object_properties[H.partOf].characteristics == ["TransitiveProperty"]
    assert "SymmetricProperty" in service.object_properties[H.interactsWith].characteristics
    assert "IrreflexiveProperty" in service.object_properties[H.interactsWith].characteristics
    assert service.object_properties[H.treatsPatient].inverse == H.treatedBy


def test_individuals_and_identifiers(service):
    assert len(service.individuals) >= 100
    assert service.count_instances(H.Patient) == 12
    assert service.count_instances(H.Doctor) == 10
    assert service.count_instances(H.Disease) >= 10
    john = URIRef(str(H) + "p001")
    assert service.label(john) == "John Miller"
    assert str(service.values(john, H.patientId)[0]) == "P-1001"


def test_object_and_data_property_values(service):
    john = URIRef(str(H) + "p001")
    doctors = {service.label(d) for d in service.objects(john, H.treatedBy)}
    assert "Dr. Alice Chen" in doctors
    diseases = {service.label(d) for d in service.objects(john, H.diagnosedWith)}
    assert {"Type 2 Diabetes", "Hypertension"} <= diseases
    assert str(service.values(john, H.bloodGroup)[0]) == "O+"
    assert int(service.values(john, H.age)[0]) == 68


def test_owl_restrictions_present(owl_path):
    graph = Graph()
    graph.parse(str(owl_path), format="xml")
    restrictions = list(graph.subjects(RDF.type, OWL.Restriction))
    assert len(restrictions) >= 8

    some_values = {p for r in restrictions for p in graph.objects(r, OWL.someValuesFrom)}
    assert H.ChronicDisease in some_values
    assert H.Diabetes in some_values

    # Cardinality restriction used by PatientWithComorbidities / BusyDoctor.
    cardinalities = list(graph.objects(None, OWL.minQualifiedCardinality))
    assert {int(v) for v in cardinalities} >= {2}

    # OWL 2 datatype facet used by SeniorPatient (age >= 65).
    datatypes = list(graph.objects(None, OWL.onDatatype))
    assert XSD.integer in datatypes
    facets = list(graph.objects(None, XSD.minInclusive))
    assert {int(v) for v in facets} >= {65}


def test_all_different_axioms(owl_path):
    graph = Graph()
    graph.parse(str(owl_path), format="xml")
    all_diff = list(graph.subjects(RDF.type, OWL.AllDifferent))
    assert all_diff, "owl:AllDifferent is required for cardinality inference of patients"
    members = []
    for node in all_diff:
        members.extend(graph.items(graph.value(node, OWL.members)))
    assert len(members) >= 10


def test_sparql_endpoint(service):
    rows = service.select(
        "SELECT ?p ?name WHERE { ?p a h:Patient ; h:patientId ?name } ORDER BY ?name"
    )
    assert len(rows) == 12
    assert all("p" in row and "name" in row for row in rows)


def test_medical_record_and_prescription_links(service):
    records = list(service.graph.subjects(RDF.type, H.MedicalRecord))
    assert records, "expected at least one MedicalRecord individual"
    for record in records:
        owners = list(service.graph.subjects(H.hasMedicalRecord, record))
        assert owners, f"{record} is not linked to a patient"
        assert service.objects(record, H.hasPrescription), f"{record} has no prescription"


def test_reasoner_consistency_and_inference(agent):
    assert agent.reasoner is not None
    ok, error = agent.reasoner.run()
    assert ok, error
    ok2, _ = agent.reasoner.run()
    assert ok2, "reasoner result should be cached after the first run"
    assert agent.reasoner.inconsistent_individuals() == []

    p001 = str(H) + "p001"
    inferred = set(agent.reasoner.inferred_types(p001))
    assert {"SeniorPatient", "DiabetesPatient", "CardiovascularPatient",
            "PatientWithComorbidities"} <= inferred

    p003 = str(H) + "p003"
    assert "CardiologyPatient" in agent.reasoner.inferred_types(p003)


def test_transitive_part_of(service):
    rows = service.select(
        "SELECT ?h WHERE { h:ward_cardio_icu h:partOf+ ?h . ?h a h:Hospital }"
    )
    hospitals = {service.label(r["h"]) for r in rows}
    assert "St. Mary's Hospital" in hospitals
