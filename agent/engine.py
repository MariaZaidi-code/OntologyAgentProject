"""Ontology-aware question answering engine.

The agent never generates domain facts: every answer is computed from the
OWL graph through rdflib/SPARQL.  A question is mapped to an *intent* and a
set of ontology entities; the handler then executes graph queries and builds
a natural-language answer together with the SPARQL query and supporting triples.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

from rdflib import Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from .ontology import (
    H,
    STOPWORDS,
    EntityMatch,
    OntologyService,
    PathResult,
    ReasonerService,
    normalize,
)


@dataclass
class Answer:
    text: str
    intent: str
    confidence: float = 0.85
    evidence: list[tuple] = field(default_factory=list)
    sparql: Optional[str] = None
    entities: list[str] = field(default_factory=list)
    ok: bool = True

    @property
    def evidence_text(self) -> str:
        if not self.evidence:
            return ""
        lines = []
        for s, p, o in self.evidence[:8]:
            lines.append(f"- {self._t(s)} **{self._p(p)}** {self._t(o)}")
        return "\n".join(lines)

    @staticmethod
    def _t(x) -> str:
        return str(x)

    @staticmethod
    def _p(p) -> str:
        return str(p).split("#")[-1].replace("_", " ")


# Property-specific keyword boosts used to disambiguate relation questions.
KEYWORD_BOOSTS = {
    "allergic": {"allergicTo": 30},
    "allergy": {"allergicTo": 30},
    "interact": {"interactsWith": 30},
    "interaction": {"interactsWith": 30},
    "prescribed": {"prescribedBy": 14, "prescribedFor": 14},
    "insurance": {"hasInsurance": 20, "coversDisease": 20},
    "appointment": {"hasAppointment": 20, "hasScheduledAppointment": 20, "forPatient": 12, "withDoctor": 12},
    "specialty": {"specialty": 20},
    "license": {"licenseNumber": 20},
    "head": {"headOf": 30},
    "work": {"worksIn": 12, "affiliatedWith": 4},
    "treat": {"treatsDisease": 14, "treatsPatient": 14, "treatedBy": 10},
    "symptom": {"hasSymptom": 16, "causes": 10},
    "disease": {"diagnosedWith": 12, "treatsDisease": 8},
    "department": {"worksIn": 12, "headOf": 8, "partOf": 6},
    "hospital": {"affiliatedWith": 8, "partOf": 8},
    "medical record": {"hasMedicalRecord": 20, "recordsDiagnosis": 10, "hasPrescription": 10},
}

CLASS_NOUNS = {
    "patient": H.Patient,
    "patients": H.Patient,
    "doctor": H.Doctor,
    "doctors": H.Doctor,
    "physician": H.Doctor,
    "physicians": H.Doctor,
    "nurse": H.Nurse,
    "nurses": H.Nurse,
    "disease": H.Disease,
    "diseases": H.Disease,
    "condition": H.Disease,
    "conditions": H.Disease,
    "diagnosis": H.Disease,
    "diagnoses": H.Disease,
    "medication": H.Medication,
    "medications": H.Medication,
    "drug": H.Medication,
    "drugs": H.Medication,
    "symptom": H.Symptom,
    "symptoms": H.Symptom,
    "appointment": H.Appointment,
    "appointments": H.Appointment,
    "department": H.Department,
    "departments": H.Department,
    "hospital": H.Hospital,
    "hospitals": H.Hospital,
    "insurance": H.InsurancePlan,
    "insurance plan": H.InsurancePlan,
    "insurance plans": H.InsurancePlan,
    "medical record": H.MedicalRecord,
    "medical records": H.MedicalRecord,
    "ward": H.Ward,
    "wards": H.Ward,
    "body system": H.BodySystem,
    "body systems": H.BodySystem,
}


class OntologyAgent:
    """A lightweight, ontology-grounded question answering agent."""

    def __init__(self, owl_path: str, java_home: Optional[str] = None, reasoning: bool = False):
        self.onto = OntologyService(owl_path)
        self.java_home = java_home
        self.reasoner: Optional[ReasonerService] = None
        if reasoning:
            self.reasoner = ReasonerService(owl_path, java_home)
        self.last_person: Optional[URIRef] = None
        self.last_entities: list[str] = []

    # ------------------------------------------------------------- utilities
    def _join(self, items: Iterable[str]) -> str:
        items = [i for i in items if i]
        if not items:
            return "none"
        if len(items) == 1:
            return items[0]
        if len(items) == 2:
            return f"{items[0]} and {items[1]}"
        return ", ".join(items[:-1]) + ", and " + items[-1]

    def _plural(self, label: str) -> str:
        if label.endswith("s"):
            return label
        if label.endswith("y"):
            return label[:-1] + "ies"
        return label + "s"

    def _labels(self, uris: Iterable[URIRef]) -> list[str]:
        return [self.onto.label(u) for u in uris]

    def _ind(self, matches: list[EntityMatch]) -> Optional[URIRef]:
        for m in matches:
            if m.kind == "individual":
                return m.uri
        return None

    def _inds(self, matches: list[EntityMatch]) -> list[URIRef]:
        return [m.uri for m in matches if m.kind == "individual"]

    def _classes(self, matches: list[EntityMatch]) -> list[URIRef]:
        return [m.uri for m in matches if m.kind == "class"]

    def _target_classes(self, matches: list[EntityMatch], norm: str) -> list[URIRef]:
        """Classes mentioned explicitly, plus common nouns found in the question."""
        classes = self._classes(matches)
        for noun, cls in CLASS_NOUNS.items():
            if re.search(rf"\b{re.escape(noun)}\b", norm) and cls not in classes:
                classes.append(cls)
        return classes

    def _most_specific_class(self, classes: list[URIRef]) -> Optional[URIRef]:
        """Pick the most specific class (drops classes that are superclasses of another)."""
        keep = []
        for c in classes:
            if any(c != o and self.onto.is_subclass(o, c) for o in classes):
                continue
            keep.append(c)
        if keep:
            return sorted(keep, key=lambda u: self.onto.label(u).lower())[0]
        return classes[0] if classes else None

    def _inferred_instances(self, cls: URIRef) -> list[URIRef]:
        if self.reasoner is None or not self.reasoner.run()[0]:
            return []
        local = self.onto.local(cls)
        return [ind for ind in self.onto.individuals
                if local in self.reasoner.inferred_types(str(ind))]

    def _props(self, matches: list[EntityMatch], kind: Optional[str] = None) -> list[URIRef]:
        out = []
        for m in matches:
            if m.kind in ("object_property", "data_property") and (kind is None or m.kind == kind):
                out.append(m.uri)
        return out

    def _answer(self, text: str, intent: str, evidence: Optional[list[tuple]] = None,
                sparql: Optional[str] = None, confidence: float = 0.9,
                entities: Optional[list[str]] = None, ok: bool = True) -> Answer:
        ans = Answer(text=text, intent=intent, evidence=evidence or [], sparql=sparql,
                     confidence=confidence, entities=entities or [], ok=ok)
        self.last_entities = ans.entities
        return ans

    def _type_label(self, uri: URIRef) -> str:
        if uri in self.onto.classes:
            return self.onto.classes[uri].label
        return self.onto.label(uri)

    def _triples_for(self, pairs: list[tuple]) -> list[tuple]:
        return [(s, p, o) for s, p, o in pairs if isinstance(s, URIRef)]

    # ------------------------------------------------------------- entry point
    def ask(self, question: str) -> Answer:
        q = question.strip()
        if not q:
            return self._answer("Please ask a question about the hospital ontology.",
                                "empty", ok=False, confidence=0.0)
        norm = normalize(q)
        matches = self.onto.match_entities(q)

        # Resolve pronouns using the previous turn.
        if re.search(r"\b(he|she|his|her|him|they|them)\b", norm) and self.last_person is not None \
                and not any(m.kind == "individual" for m in matches):
            matches = matches + [EntityMatch("individual", self.last_person,
                                             self.onto.label(self.last_person), 0, 0)]

        handlers: list[tuple[str, Callable[[str, str, list[EntityMatch]], Optional[Answer]]]] = [
            ("help", self._q_help),
            ("statistics", self._q_stats),
            ("list_schema", self._q_list_schema),
            ("subclass_check", self._q_subclass_check),
            ("superclass", self._q_superclass),
            ("subclasses", self._q_subclasses),
            ("count", self._q_count),
            ("superlative", self._q_superlative),
            ("attribute", self._q_attribute),
            ("relationship_between", self._q_relationship_between),
            ("hospital_of_doctor", self._q_hospital_of_doctor),
            ("symptoms_of_patient", self._q_symptoms_of_patient),
            ("symptoms_of_disease", self._q_symptoms_of_disease),
            ("symptoms_from_patient_diseases", self._q_symptoms_from_patient_diseases),
            ("drug_interactions", self._q_drug_interactions),
            ("interactions_of_patient_meds", self._q_interactions_of_patient_meds),
            ("patients_of_doctor", self._q_patients_of_doctor),
            ("patients_by_specialty", self._q_patients_by_specialty),
            ("diseases_treated_by_doctor", self._q_diseases_treated_by_doctor),
            ("patients_with_appointment", self._q_patients_with_appointment),
            ("appointments_of_doctor", self._q_appointments_of_doctor),
            ("diseases_by_system", self._q_diseases_by_system),
            ("diseases_treated_with", self._q_diseases_treated_with),
            ("patients_allergic", self._q_patients_allergic),
            ("patients_with_disease", self._q_patients_with_disease),
            ("patient_diseases", self._q_patient_diseases),
            ("patient_medications", self._q_patient_medications),
            ("medications_prescribed_by", self._q_medications_prescribed_by),
            ("insurance_coverage", self._q_insurance_coverage),
            ("patients_with_insurance", self._q_patients_with_insurance),
            ("head_of_department", self._q_head_of_department),
            ("doctors_in_department", self._q_doctors_in_department),
            ("workers_in_hospital", self._q_workers_in_hospital),
            ("comorbidity_count", self._q_comorbidity_count),
            ("yes_no", self._q_yes_no),
            ("instances", self._q_instances),
            ("generic_relation", self._q_generic_relation),
            ("class_description", self._q_class_description),
            ("individual_description", self._q_individual_description),
        ]
        for name, handler in handlers:
            ans = handler(q, norm, matches)
            if ans is not None:
                if ans.entities:
                    for e in ans.entities:
                        if e in self.onto.individuals:
                            self.last_person = self.onto.individuals[e].uri
                return ans

        return self._unknown(q)

    def _unknown(self, q: str) -> Answer:
        return self._answer(
            f"I could not find an answer to **\"{q}\"** in the hospital ontology.\n\n"
            "I only answer from facts stored in `hospital_ontology.owl`; I do not guess or "
            "invent information. Try asking about patients, doctors, diseases, symptoms, "
            "medications, departments, appointments or insurance plans (or type `help`).",
            "unknown", ok=False, confidence=0.0)

    # ------------------------------------------------------------- handlers
    def _q_help(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        if norm in {"hi", "hello", "hey", "help", "what can you do", "how does this work",
                    "what can i ask", "commands"} or norm.startswith("help me"):
            return self._answer(
                "**Hospital Ontology Agent**\n\n"
                "I answer questions using the facts and the class hierarchy in "
                "`hospital_ontology.owl`. Examples:\n"
                "- *Who is John Miller?*  (entity lookup)\n"
                "- *What is a Cardiologist?*  (class definition)\n"
                "- *List all subclasses of Disease.*  (class hierarchy)\n"
                "- *Who is the doctor of Robert Brown?*  (relationship)\n"
                "- *What is John Miller's blood group?*  (attribute)\n"
                "- *Which symptoms are caused by diseases that John Miller has?*  (multi-hop)\n"
                "- *Which hospital does Dr. Patel work at?*  (transitive path)\n"
                "- *Which medications interact with Aspirin?*  (symmetric property)\n"
                "- *How many patients are there?*  (count)\n"
                "- *Who is the head of the Cardiology department?*  (inverse property)\n\n"
                "Commands: `stats`, `classes`, `properties`, `reason`, `clear`, `exit`.",
                "help", confidence=1.0)
        return None

    def _q_stats(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        if not re.search(r"\b(stats|statistics|how many individuals|what is in the ontology)\b", norm):
            return None
        s = self.onto.stats()
        lines = [
            "**Ontology statistics**",
            f"- Classes: **{s['classes']}**",
            f"- Object properties: **{s['object_properties']}**",
            f"- Data properties: **{s['data_properties']}**",
            f"- Individuals: **{s['individuals']}**",
            f"- RDF triples: **{s['triples']}**",
            "",
            f"Patients: {s['patients']} | Doctors: {s['doctors']} | Diseases: {s['diseases']} | "
            f"Medications: {s['medications']} | Appointments: {s['appointments']}",
        ]
        return self._answer("\n".join(lines), "statistics", confidence=1.0)

    def _q_list_schema(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        if not re.search(r"\b(list|show)\b", norm):
            return None
        if re.search(r"\bclasses\b", norm) and not re.search(r"\b(patients|doctors|diseases|medications|appointments|individuals)\b", norm):
            lines = ["**Classes in the ontology**"]
            for c in self.onto.named_classes():
                lines.append(f"- {self.onto.label(c)} ({self.onto.count_instances(c)} individuals)")
            return self._answer("\n".join(lines), "list_classes", confidence=1.0)
        if re.search(r"\b(object properties|properties)\b", norm) and "data" not in norm:
            lines = ["**Object properties**"]
            for p in sorted(self.onto.object_properties.values(), key=lambda x: x.label.lower()):
                dom, rng = p.domain, p.range
                if not dom and p.inverse and p.inverse in self.onto.object_properties:
                    inv = self.onto.object_properties[p.inverse]
                    dom, rng = inv.range, inv.domain
                dom_s = self._join(self._labels(dom)) if dom else "-"
                rng_s = self._join(self._labels(rng)) if rng else "-"
                lines.append(f"- **{p.label}**: {dom_s} -> {rng_s}")
            return self._answer("\n".join(lines), "list_object_properties", confidence=1.0)
        if re.search(r"\bdata properties\b", norm):
            lines = ["**Data properties**"]
            for p in sorted(self.onto.data_properties.values(), key=lambda x: x.label.lower()):
                dom = self._join(self._labels(p.domain)) if p.domain else "-"
                rng = p.range[0].split("#")[-1] if p.range else "-"
                lines.append(f"- **{p.label}**: {dom} → {rng}")
            return self._answer("\n".join(lines), "list_data_properties", confidence=1.0)
        return None

    def _q_subclass_check(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        if not re.search(r"\bis\b.*\b(subclass|subtype|type|kind)\b", norm) and not re.search(r"\bare\b.*\b(subclasses|types|kinds)\b", norm):
            return None
        inds = self._inds(matches)
        classes = self._classes(matches)
        if len(classes) >= 2:
            child, parent = classes[0], classes[1]
            yes = self.onto.is_subclass(child, parent)
            query = f"ASK {{ h:{self.onto.local(child)} rdfs:subClassOf* h:{self.onto.local(parent)} }}"
            text = (f"**Yes.** {self.onto.label(child)} is a subclass of {self.onto.label(parent)} "
                    f"(directly or through intermediate classes)." if yes else
                    f"**No.** {self.onto.label(child)} is not a subclass of {self.onto.label(parent)}.")
            return self._answer(text, "subclass_check", sparql=query, confidence=1.0 if yes else 0.95)
        if inds and classes:
            ind, cls = inds[0], classes[-1]
            yes = self.onto.instance_of(ind, cls)
            query = f"ASK {{ h:{self.onto.local(ind)} rdf:type/rdfs:subClassOf* h:{self.onto.local(cls)} }}"
            types = self._join(self._labels(self.onto.types_of(ind)))
            if yes:
                subs = [t for t in self.onto.types_of(ind) if self.onto.is_subclass(t, cls)]
                if subs:
                    text = (f"**Yes.** {self.onto.label(ind)} is a {self.onto.label(cls)} — its recorded types "
                            f"({self._join(self._labels(subs))}) are subclasses of {self.onto.label(cls)}.")
                else:
                    text = f"**Yes.** {self.onto.label(ind)} is a {self.onto.label(cls)}."
            else:
                text = (f"**No.** {self.onto.label(ind)} is not a {self.onto.label(cls)}; "
                        f"its recorded types are: {types}.")
            return self._answer(text, "subclass_check", sparql=query, confidence=1.0)
        return None

    def _q_superclass(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        classes = self._classes(matches)
        if not classes:
            return None
        if re.search(r"\b(superclasses|parent classes|base classes)\b", norm) or \
                re.search(r"\bsubclass of\b", norm):
            cls = classes[0]
            supers = self.onto.direct_superclasses(cls)
            if not supers:
                return self._answer(f"{self.onto.label(cls)} has no named superclass.", "superclass")
            lines = [f"**{self.onto.label(cls)}** is a subclass of:"]
            lines += [f"- {self.onto.label(s)}" for s in supers]
            return self._answer("\n".join(lines), "superclass", confidence=1.0)
        return None

    def _q_subclasses(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        classes = self._classes(matches)
        if not classes or not re.search(r"\b(subclasses|child classes|subtypes)\b", norm):
            return None
        cls = classes[0]
        if re.search(r"\b(all|entire|full)\b", norm):
            subs = self.onto.all_subclasses(cls)
            title = f"**All subclasses of {self.onto.label(cls)}**"
            query = f"SELECT ?c WHERE {{ ?c rdfs:subClassOf+ h:{self.onto.local(cls)} }}"
        else:
            subs = self.onto.direct_subclasses(cls)
            title = f"**Direct subclasses of {self.onto.label(cls)}**"
            query = f"SELECT ?c WHERE {{ ?c rdfs:subClassOf h:{self.onto.local(cls)} }}"
        if not subs:
            n = self.onto.count_instances(cls)
            extra = (f" {n} individual(s) are typed as {self.onto.label(cls)} or one of its subclasses."
                     if n else "")
            return self._answer(f"{self.onto.label(cls)} has no subclasses in the ontology." + extra,
                                "subclasses", confidence=1.0)
        lines = [title] + [f"- {self.onto.label(s)}" for s in subs]
        n = self.onto.count_instances(cls)
        if len(subs) == 1:
            lines.append(f"\nNote: {n} individual(s) are typed as {self.onto.label(cls)} or its subclasses.")
        return self._answer("\n".join(lines), "subclasses", sparql=query, confidence=1.0)

    def _q_count(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        if not re.search(r"\bhow many\b", norm):
            return None
        # how many X are there
        m = re.search(r"how many ([a-z ]+?) (are there|is there|exist)", norm)
        if m:
            noun = m.group(1).strip()
            cls = CLASS_NOUNS.get(noun)
            if cls:
                n = self.onto.count_instances(cls)
                return self._answer(f"There are **{n}** {noun} in the ontology.",
                                    "count_instances", confidence=1.0)
        # how many <class> does <individual> have/treat...
        classes = self._target_classes(matches, norm)
        inds = self._inds(matches)
        if inds and classes:
            ind, cls = inds[0], classes[0]
            prop = self._select_property(ind, cls, norm)
            if prop:
                vals, used, inv = self._relation_values_auto(ind, cls, prop[0])
                vals = sorted(vals, key=lambda v: self.onto.label(v))
                return self._answer(
                    f"{self.onto.label(ind)} has **{len(vals)}** {self.onto.label(cls).lower()}"
                    f"{'s' if len(vals) != 1 else ''}: {self._join(self._labels(vals))}.",
                    "count_relation", confidence=0.95)
        # how many <class1> have <class2>  (e.g. how many patients have diabetes)
        if len(classes) >= 2:
            patient_cls = next((c for c in classes if self.onto.is_subclass(c, H.Patient)), None)
            disease_cls = next((c for c in classes if self.onto.is_subclass(c, H.Disease)), None)
            if patient_cls and disease_cls:
                rows = self.onto.select(
                    "SELECT DISTINCT ?p WHERE { ?p h:diagnosedWith ?d . "
                    f"?d rdf:type/rdfs:subClassOf* h:{self.onto.local(disease_cls)} }}")
                n = len(rows)
                return self._answer(
                    f"**{n}** patient(s) have a disease of type **{self.onto.label(disease_cls)}**.",
                    "count_patients_with_disease", confidence=0.95)
        return None

    def _q_superlative(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        m = re.search(r"\b(oldest|youngest|most expensive|least expensive|cheapest|highest|lowest)\b", norm)
        if not m:
            return None
        word = m.group(1)
        cls = None
        prop = None
        order = "DESC"
        if word in {"oldest", "youngest"}:
            cls, prop, order = H.Patient, H.age, "DESC" if word == "oldest" else "ASC"
            if self._classes(matches):
                cls = self._classes(matches)[0]
        elif word in {"most expensive", "least expensive", "cheapest"}:
            cls, prop, order = H.Medication, H.cost, "ASC" if word in {"least expensive", "cheapest"} else "DESC"
        elif word in {"highest", "lowest"}:
            cls, prop, order = H.InsurancePlan, H.coveragePercentage, "DESC" if word == "highest" else "ASC"
        query = (f"SELECT ?x ?v WHERE {{ ?x rdf:type/rdfs:subClassOf* h:{self.onto.local(cls)} ; "
                 f"h:{self.onto.local(prop)} ?v }} ORDER BY {order}(?v) LIMIT 1")
        rows = self.onto.select(query)
        if not rows:
            return self._answer("No matching individuals were found.", "superlative", ok=False)
        row = rows[0]
        return self._answer(
            f"**{self.onto.label(row['x'])}** is the {word} with value **{self.onto.fmt_value(row['v'])}**.",
            "superlative", sparql=query, confidence=1.0,
            evidence=[(row["x"], prop, row["v"])])

    def _q_attribute(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        inds = self._inds(matches)
        if not inds:
            return None
        # Only treat as an attribute question when it has an attribute-like shape.
        if not re.match(r"^(what|how|whose)\b", norm):
            return None
        if not (re.search(r"\bof\b", norm) or "'s" in q.lower() or re.search(r"\bhow old\b", norm)
                or re.search(r"\bwhat\b.*\b(have|has)\b", norm)):
            return None
        prop = self.onto.find_data_property(q)
        if prop is None:
            return None
        prop_uri, alias, _ = prop
        subj = inds[0]
        vals = self.onto.values(subj, prop_uri)
        if not vals:
            return None
        query = f"SELECT ?v WHERE {{ h:{self.onto.local(subj)} h:{self.onto.local(prop_uri)} ?v }}"
        label = self.onto.label(prop_uri)
        label = label[:1].upper() + label[1:]
        text = f"**{label} of {self.onto.label(subj)}:** " + ", ".join(f"**{self.onto.fmt_value(v)}**" for v in vals)
        ev = [(subj, prop_uri, v) for v in vals]
        return self._answer(text, "attribute", sparql=query, evidence=ev, confidence=0.98,
                            entities=[self.onto.label(subj)])

    def _q_relationship_between(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        if not re.search(r"\b(between|related to|relationship)\b", norm):
            return None
        inds = self._inds(matches)
        if len(inds) < 2:
            return None
        a, b = inds[0], inds[1]
        paths = self._paths_between(a, b, max_depth=3)
        if not paths:
            return self._answer(
                f"No relationship path between {self.onto.label(a)} and {self.onto.label(b)} "
                "was found in the ontology.", "relationship_between", ok=False)
        p = paths[0]
        desc = p.describe(self.onto)
        return self._answer(
            f"**Relationship path:** {desc}\n\n"
            f"{self.onto.label(a)} and {self.onto.label(b)} are connected through "
            f"{len(p.predicates)} ontology relationship(s).",
            "relationship_between", confidence=0.95)

    # ------------------------------------------------------- multi-hop queries
    def _q_hospital_of_doctor(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        if not re.search(r"\b(hospital|where)\b", norm):
            return None
        inds = self._inds(matches)
        if not inds or not re.search(r"\b(work|works|working)\b", norm):
            return None
        doc = inds[0]
        if not self.onto.instance_of(doc, H.Doctor):
            return None
        depts = self.onto.objects(doc, H.worksIn)
        hospitals = []
        for d in depts:
            hospitals += list(self.onto.graph.objects(d, H.partOf))
        aff = self.onto.objects(doc, H.affiliatedWith)
        query = ("SELECT ?h WHERE { h:" + self.onto.local(doc) + " h:worksIn/h:partOf ?h . "
                 "?h rdf:type/rdfs:subClassOf* h:Hospital }")
        if not hospitals and not aff:
            return None
        ev = [(doc, H.worksIn, d) for d in depts] + [(doc, H.affiliatedWith, h) for h in aff]
        text = (f"{self.onto.label(doc)} works in **{self._join(self._labels(depts))}**, which is part of "
                f"**{self._join(self._labels(hospitals))}**.")
        if aff:
            text += f" The doctor is also affiliated with {self._join(self._labels(aff))}."
        return self._answer(text, "hospital_of_doctor", sparql=query, evidence=ev,
                            confidence=0.98, entities=[self.onto.label(doc)])

    def _q_symptoms_of_patient(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        inds = self._inds(matches)
        if not inds or not re.search(r"\b(symptoms?)\b", norm):
            return None
        pat = inds[0]
        if not self.onto.instance_of(pat, H.Patient):
            return None
        if re.search(r"\b(caused|due to|diseases?)\b", norm):
            return None
        syms = self.onto.objects(pat, H.hasSymptom)
        if not syms:
            return None
        query = f"SELECT ?s WHERE {{ h:{self.onto.local(pat)} h:hasSymptom ?s }}"
        return self._answer(
            f"{self.onto.label(pat)} has the following recorded symptoms: "
            + self._join([f"{self.onto.label(s)} (severity {self._sev(s)})" for s in syms]) + ".",
            "symptoms_of_patient", sparql=query, evidence=[(pat, H.hasSymptom, s) for s in syms],
            confidence=0.98, entities=[self.onto.label(pat)])

    def _sev(self, s: URIRef) -> str:
        vals = self.onto.values(s, H.severity)
        return str(vals[0]) if vals else "?"

    def _q_symptoms_of_disease(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        inds = self._inds(matches)
        if not inds or not re.search(r"\b(symptoms?)\b", norm):
            return None
        disease = inds[0]
        if not self.onto.instance_of(disease, H.Disease):
            return None
        syms = self.onto.objects(disease, H.causes)
        if not syms:
            return None
        query = f"SELECT ?s WHERE {{ h:{self.onto.local(disease)} h:causes ?s }}"
        return self._answer(
            f"**{self.onto.label(disease)}** causes: " + self._join(self._labels(syms)) + ".",
            "symptoms_of_disease", sparql=query, evidence=[(disease, H.causes, s) for s in syms],
            confidence=0.98)

    def _q_symptoms_from_patient_diseases(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        inds = self._inds(matches)
        if not inds or not re.search(r"\b(symptoms?)\b", norm):
            return None
        pat = inds[0]
        if not self.onto.instance_of(pat, H.Patient):
            return None
        if not re.search(r"\b(diseases?|conditions?|diagnos\w+)\b", norm):
            return None
        diseases = self.onto.objects(pat, H.diagnosedWith)
        if not diseases:
            return None
        syms = []
        for d in diseases:
            syms += list(self.onto.objects(d, H.causes))
        # de-duplicate, keep order
        seen, uniq = set(), []
        for s in syms:
            if s not in seen:
                seen.add(s)
                uniq.append(s)
        query = ("SELECT DISTINCT ?s WHERE { h:" + self.onto.local(pat) + " h:diagnosedWith ?d . "
                 "?d h:causes ?s }")
        ev = [(pat, H.diagnosedWith, d) for d in diseases] + [(d, H.causes, s) for d in diseases for s in self.onto.objects(d, H.causes)]
        return self._answer(
            f"{self.onto.label(pat)} has **{self._join(self._labels(diseases))}**. "
            f"Symptoms caused by these diseases: **{self._join(self._labels(uniq))}**.",
            "symptoms_from_patient_diseases", sparql=query, evidence=ev,
            confidence=0.97, entities=[self.onto.label(pat)])

    def _q_drug_interactions(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        if not re.search(r"\b(interact|interacts|interactions?)\b", norm):
            return None
        inds = self._inds(matches)
        if not inds:
            return None
        med = inds[0]
        if not self.onto.instance_of(med, H.Medication):
            return None
        others = [o for o in self.onto.objects(med, H.interactsWith) if o != med]
        # symmetric property: also look for incoming assertions
        others += [s for s in self.onto.subjects(med, H.interactsWith) if s != med]
        seen, uniq = set(), []
        for o in others:
            if o not in seen:
                seen.add(o)
                uniq.append(o)
        if not uniq:
            return self._answer(
                f"**{self.onto.label(med)}** has no recorded drug interactions in the ontology.",
                "drug_interactions", confidence=0.95)
        query = f"SELECT ?o WHERE {{ {{ h:{self.onto.local(med)} h:interactsWith ?o }} UNION {{ ?o h:interactsWith h:{self.onto.local(med)} }} }}"
        return self._answer(
            f"**{self.onto.label(med)}** interacts with: " + self._join(self._labels(uniq)) + ".",
            "drug_interactions", sparql=query,
            evidence=[(med, H.interactsWith, o) for o in uniq], confidence=0.98)

    def _q_interactions_of_patient_meds(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        inds = self._inds(matches)
        if not inds or not re.search(r"\b(interact|interactions?)\b", norm):
            return None
        pat = inds[0]
        if not self.onto.instance_of(pat, H.Patient):
            return None
        meds = list(self.onto.subjects(pat, H.prescribedFor))
        meds += list(self.onto.objects(self.onto.objects(pat, H.hasMedicalRecord)[0], H.hasPrescription)) \
            if self.onto.objects(pat, H.hasMedicalRecord) else []
        seen, uniq = set(), []
        for m in meds:
            if m not in seen:
                seen.add(m)
                uniq.append(m)
        if not uniq:
            return self._answer(f"No medications are prescribed for {self.onto.label(pat)}.",
                                "interactions_of_patient_meds", ok=False)
        interactions = []
        for m in uniq:
            others = [o for o in self.onto.objects(m, H.interactsWith) if o != m]
            others += [s for s in self.onto.subjects(m, H.interactsWith) if s != m]
            for o in others:
                interactions.append((m, o))
        if not interactions:
            return self._answer(
                f"{self.onto.label(pat)} takes **{self._join(self._labels(uniq))}**; none of these "
                "medications has a recorded interaction in the ontology.",
                "interactions_of_patient_meds", confidence=0.95)
        lines = [f"**{self.onto.label(pat)}** takes: {self._join(self._labels(uniq))}.", "", "Recorded interactions:"]
        for m, o in interactions:
            lines.append(f"- {self.onto.label(m)} interacts with {self.onto.label(o)}")
        query = ("SELECT ?m ?o WHERE { ?m h:prescribedFor h:" + self.onto.local(pat) + " . "
                 "{ ?m h:interactsWith ?o } UNION { ?o h:interactsWith ?m } }")
        return self._answer("\n".join(lines), "interactions_of_patient_meds", sparql=query,
                            evidence=[(m, H.interactsWith, o) for m, o in interactions],
                            confidence=0.97, entities=[self.onto.label(pat)])

    def _q_patients_of_doctor(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        inds = self._inds(matches)
        if not inds or not re.search(r"\b(patients?|people)\b", norm):
            return None
        doc = inds[0]
        if not self.onto.instance_of(doc, H.Doctor):
            return None
        if not re.search(r"\b(treat|treats|treating|see|sees|doctor)\b", norm):
            return None
        patients = list(self.onto.subjects(doc, H.treatedBy))
        query = f"SELECT ?p WHERE {{ ?p h:treatedBy h:{self.onto.local(doc)} }}"
        if not patients:
            return None
        return self._answer(
            f"**{self.onto.label(doc)}** treats: " + self._join(self._labels(patients)) + ".",
            "patients_of_doctor", sparql=query, evidence=[(p, H.treatedBy, doc) for p in patients],
            confidence=0.98, entities=[self.onto.label(doc)])

    def _q_patients_by_specialty(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        classes = self._classes(matches)
        if not classes or not re.search(r"\b(patients?|people)\b", norm):
            return None
        if not re.search(r"\b(treated by|see|sees|treated|doctor|specialist|cardiologist|neurologist)\b", norm):
            return None
        cls = None
        for c in classes:
            if self.onto.is_subclass(c, H.Doctor) or c == H.Doctor:
                cls = c
                break
        if cls is None:
            return None
        rows = self.onto.select(
            "SELECT DISTINCT ?p ?d WHERE { ?p h:treatedBy ?d . ?d rdf:type/rdfs:subClassOf* h:" +
            self.onto.local(cls) + " }")
        pairs = [(r["p"], r["d"]) for r in rows if isinstance(r["p"], URIRef) and isinstance(r["d"], URIRef)]
        patients = sorted({p for p, _ in pairs}, key=lambda u: self.onto.label(u))
        if not patients:
            return self._answer(f"No patients are treated by a {self.onto.label(cls)} in the ontology.",
                                "patients_by_specialty", confidence=0.95)
        return self._answer(
            f"Patients treated by a **{self.onto.label(cls)}**: " + self._join(self._labels(patients)) + ".",
            "patients_by_specialty",
            sparql="SELECT DISTINCT ?p WHERE { ?p h:treatedBy ?d . ?d rdf:type/rdfs:subClassOf* h:" + self.onto.local(cls) + " }",
            evidence=[(p, H.treatedBy, d) for p, d in pairs], confidence=0.97)

    def _q_diseases_treated_by_doctor(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        inds = self._inds(matches)
        classes = self._classes(matches)
        if not inds or not classes or not re.search(r"\b(diseases?|conditions?)\b", norm):
            return None
        doc = inds[0]
        if not self.onto.instance_of(doc, H.Doctor) or not re.search(r"\b(treat|treats|treating)\b", norm):
            return None
        diseases = self.onto.objects(doc, H.treatsDisease)
        if not diseases:
            return None
        return self._answer(
            f"**{self.onto.label(doc)}** treats: " + self._join(self._labels(diseases)) + ".",
            "diseases_treated_by_doctor", sparql=f"SELECT ?d WHERE {{ h:{self.onto.local(doc)} h:treatsDisease ?d }}",
            evidence=[(doc, H.treatsDisease, d) for d in diseases], confidence=0.98,
            entities=[self.onto.label(doc)])

    def _q_patients_with_appointment(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        inds = self._inds(matches)
        if not inds or not re.search(r"\b(patients?|people)\b", norm):
            return None
        doc = inds[0]
        if not self.onto.instance_of(doc, H.Doctor) or not re.search(r"\b(appointment|appointments)\b", norm):
            return None
        rows = self.onto.select(
            "SELECT DISTINCT ?p ?a WHERE { ?a h:withDoctor h:" + self.onto.local(doc) +
            " . ?a h:forPatient ?p }")
        pairs = [(r["p"], r["a"]) for r in rows if isinstance(r["p"], URIRef) and isinstance(r["a"], URIRef)]
        patients = sorted({p for p, _ in pairs}, key=lambda u: self.onto.label(u))
        if not patients:
            return None
        return self._answer(
            f"Patients with an appointment with **{self.onto.label(doc)}**: " +
            self._join(self._labels(patients)) + ".",
            "patients_with_appointment",
            sparql="SELECT DISTINCT ?p WHERE { ?a h:withDoctor h:" + self.onto.local(doc) + " . ?a h:forPatient ?p }",
            evidence=[(p, H.hasAppointment, a) for p, a in pairs], confidence=0.97,
            entities=[self.onto.label(doc)])

    def _q_appointments_of_doctor(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        inds = self._inds(matches)
        if not inds or not re.search(r"\b(appointments?)\b", norm):
            return None
        doc = inds[0]
        if not self.onto.instance_of(doc, H.Doctor):
            return None
        appts = list(self.onto.subjects(doc, H.withDoctor))
        if not appts:
            return None
        lines = [f"**{self.onto.label(doc)}** has {len(appts)} appointment(s):"]
        def _date(a):
            d = next(self.onto.graph.objects(a, H.appointmentDate), None)
            return str(d) if d is not None else ""
        for a in sorted(appts, key=_date):
            date = self.onto.fmt_value(next(self.onto.graph.objects(a, H.appointmentDate), ""))
            patient = self.onto.label(next(self.onto.graph.objects(a, H.forPatient), a))
            status = self.onto.fmt_value(next(self.onto.graph.objects(a, H.status), ""))
            lines.append(f"- {self.onto.label(a)} — {date} — patient {patient} ({status})")
        return self._answer("\n".join(lines), "appointments_of_doctor",
                            evidence=[(a, H.withDoctor, doc) for a in appts], confidence=0.98,
                            entities=[self.onto.label(doc)])

    def _q_diseases_by_system(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        inds = self._inds(matches)
        if not inds or not re.search(r"\b(diseases?|conditions?)\b", norm):
            return None
        system = inds[0]
        if not self.onto.instance_of(system, H.BodySystem):
            return None
        diseases = list(self.onto.subjects(system, H.hasAffectedSystem))
        if not diseases:
            return None
        return self._answer(
            f"Diseases affecting the **{self.onto.label(system)}**: " +
            self._join(sorted(self._labels(diseases))) + ".",
            "diseases_by_system",
            sparql=f"SELECT ?d WHERE {{ ?d h:hasAffectedSystem h:{self.onto.local(system)} }}",
            evidence=[(d, H.hasAffectedSystem, system) for d in diseases], confidence=0.98)

    def _q_diseases_treated_with(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        inds = self._inds(matches)
        if not inds or not re.search(r"\b(diseases?|conditions?)\b", norm):
            return None
        treatment = inds[0]
        if not (self.onto.instance_of(treatment, H.Medication) or self.onto.instance_of(treatment, H.Treatment)):
            return None
        diseases = list(self.onto.subjects(treatment, H.treatedWith))
        if not diseases:
            return None
        return self._answer(
            f"Diseases treated with **{self.onto.label(treatment)}**: " +
            self._join(sorted(self._labels(diseases))) + ".",
            "diseases_treated_with",
            sparql=f"SELECT ?d WHERE {{ ?d h:treatedWith h:{self.onto.local(treatment)} }}",
            evidence=[(d, H.treatedWith, treatment) for d in diseases], confidence=0.98)

    def _q_patients_allergic(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        inds = self._inds(matches)
        if not inds or not re.search(r"\b(allerg\w*)\b", norm):
            return None
        med = inds[0]
        if not self.onto.instance_of(med, H.Medication):
            return None
        patients = list(self.onto.subjects(med, H.allergicTo))
        if not patients:
            return self._answer(f"No patients are recorded as allergic to {self.onto.label(med)}.",
                                "patients_allergic", confidence=0.95)
        return self._answer(
            f"Patients allergic to **{self.onto.label(med)}**: " + self._join(self._labels(patients)) + ".",
            "patients_allergic", sparql=f"SELECT ?p WHERE {{ ?p h:allergicTo h:{self.onto.local(med)} }}",
            evidence=[(p, H.allergicTo, med) for p in patients], confidence=0.98)

    def _q_patients_with_disease(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        inds = self._inds(matches)
        classes = self._classes(matches)
        if not inds or not classes:
            return None
        disease = inds[0]
        if not self.onto.instance_of(disease, H.Disease):
            return None
        patients = list(self.onto.subjects(disease, H.diagnosedWith))
        if not patients:
            return self._answer(f"No patients are recorded with {self.onto.label(disease)}.",
                                "patients_with_disease", confidence=0.95)
        return self._answer(
            f"Patients diagnosed with **{self.onto.label(disease)}**: " + self._join(self._labels(patients)) + ".",
            "patients_with_disease", sparql=f"SELECT ?p WHERE {{ ?p h:diagnosedWith h:{self.onto.local(disease)} }}",
            evidence=[(p, H.diagnosedWith, disease) for p in patients], confidence=0.98)

    def _q_patient_diseases(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        inds = self._inds(matches)
        if not inds:
            return None
        pat = inds[0]
        if not self.onto.instance_of(pat, H.Patient) or not re.search(r"\b(diseases?|conditions?|diagnos\w+)\b", norm):
            return None
        if re.search(r"\b(insurance|cover|covers|plan|plans)\b", norm):
            return None
        if not re.search(r"\b(what|which|list|show|name)\b", norm):
            return None
        diseases = self.onto.objects(pat, H.diagnosedWith)
        if not diseases:
            return None
        return self._answer(
            f"**{self.onto.label(pat)}** has been diagnosed with: " +
            self._join([f"{self.onto.label(d)} ({self._join(self._labels(self.onto.types_of(d)))})" for d in diseases]) + ".",
            "patient_diseases", sparql=f"SELECT ?d WHERE {{ h:{self.onto.local(pat)} h:diagnosedWith ?d }}",
            evidence=[(pat, H.diagnosedWith, d) for d in diseases], confidence=0.98,
            entities=[self.onto.label(pat)])

    def _q_patient_medications(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        inds = self._inds(matches)
        if not inds:
            return None
        pat = inds[0]
        if not self.onto.instance_of(pat, H.Patient):
            return None
        if not re.search(r"\b(medications?|medicines?|drugs?|prescri\w+|take|taking|on)\b", norm):
            return None
        meds = list(self.onto.subjects(pat, H.prescribedFor))
        if not meds:
            return None
        lines = [f"**{self.onto.label(pat)}** is prescribed:"]
        for m in meds:
            dose = self.onto.fmt_value(next(self.onto.graph.objects(m, H.dosage), ""))
            freq = self.onto.fmt_value(next(self.onto.graph.objects(m, H.frequency), ""))
            lines.append(f"- {self.onto.label(m)} — {dose}, {freq}")
        return self._answer("\n".join(lines), "patient_medications",
                            sparql=f"SELECT ?m WHERE {{ ?m h:prescribedFor h:{self.onto.local(pat)} }}",
                            evidence=[(m, H.prescribedFor, pat) for m in meds], confidence=0.98,
                            entities=[self.onto.label(pat)])

    def _q_medications_prescribed_by(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        inds = self._inds(matches)
        if not inds or not re.search(r"\b(prescrib\w*)\b", norm):
            return None
        person = inds[0]
        if self.onto.instance_of(person, H.Doctor):
            meds = list(self.onto.subjects(person, H.prescribedBy))
            what = "prescribed by"
        elif self.onto.instance_of(person, H.Patient):
            meds = list(self.onto.subjects(person, H.prescribedFor))
            what = "prescribed to"
        else:
            return None
        if not meds:
            return None
        return self._answer(
            f"Medications **{what} {self.onto.label(person)}**: " + self._join(self._labels(meds)) + ".",
            "medications_prescribed_by", sparql=f"SELECT ?m WHERE {{ ?m h:{'prescribedBy' if what == 'prescribed by' else 'prescribedFor'} h:{self.onto.local(person)} }}",
            evidence=[(m, H.prescribedBy if what == "prescribed by" else H.prescribedFor, person) for m in meds],
            confidence=0.98, entities=[self.onto.label(person)])

    def _q_insurance_coverage(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        inds = self._inds(matches)
        if not inds or not re.search(r"\binsurance\b", norm):
            return None
        pat = inds[0]
        if not self.onto.instance_of(pat, H.Patient):
            return None
        plans = self.onto.objects(pat, H.hasInsurance)
        diseases = self.onto.objects(pat, H.diagnosedWith)
        if not plans or not diseases:
            return None
        covered = []
        for d in diseases:
            for plan in self.onto.subjects(d, H.coversDisease):
                covered.append((plan, d))
        lines = [f"**{self.onto.label(pat)}** is insured by " + self._join(self._labels(plans)) + "."]
        if covered:
            lines.append("Insurance plans covering the patient's recorded diseases:")
            seen = []
            for plan in [p for p, _ in covered]:
                if plan not in seen:
                    seen.append(plan)
            for plan in seen:
                ds = [d for p, d in covered if p == plan]
                lines.append(f"- {self.onto.label(plan)} covers {self._join(self._labels(ds))}")
        else:
            lines.append("None of the patient's recorded diseases is listed as covered by any plan.")
        query = ("SELECT ?plan ?d WHERE { h:" + self.onto.local(pat) + " h:diagnosedWith ?d . "
                 "?plan h:coversDisease ?d }")
        return self._answer("\n".join(lines), "insurance_coverage", sparql=query,
                            evidence=[(plan, H.coversDisease, d) for plan, d in covered],
                            confidence=0.97, entities=[self.onto.label(pat)])

    def _q_patients_with_insurance(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        inds = self._inds(matches)
        classes = self._classes(matches)
        if not inds or not classes:
            return None
        plan = inds[0]
        if not self.onto.instance_of(plan, H.InsurancePlan):
            return None
        patients = list(self.onto.subjects(plan, H.hasInsurance))
        if not patients:
            return None
        return self._answer(
            f"Patients insured by **{self.onto.label(plan)}**: " + self._join(self._labels(patients)) + ".",
            "patients_with_insurance", sparql=f"SELECT ?p WHERE {{ ?p h:hasInsurance h:{self.onto.local(plan)} }}",
            evidence=[(p, H.hasInsurance, plan) for p in patients], confidence=0.98)

    def _q_head_of_department(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        inds = self._inds(matches)
        if not inds or not re.search(r"\b(head|heads|director)\b", norm):
            return None
        dept = inds[0]
        if not self.onto.instance_of(dept, H.Department):
            return None
        heads = list(self.onto.subjects(dept, H.headOf))
        if not heads:
            return self._answer(f"No head is recorded for {self.onto.label(dept)}.", "head_of_department", ok=False)
        return self._answer(
            f"The head of **{self.onto.label(dept)}** is " + self._join(self._labels(heads)) + ".",
            "head_of_department", sparql=f"SELECT ?d WHERE {{ ?d h:headOf h:{self.onto.local(dept)} }}",
            evidence=[(d, H.headOf, dept) for d in heads], confidence=0.98)

    def _q_doctors_in_department(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        inds = self._inds(matches)
        if not inds or not re.search(r"\b(doctors?|staff|workers?|nurses?)\b", norm):
            return None
        dept = inds[0]
        if not self.onto.instance_of(dept, H.Department):
            return None
        workers = list(self.onto.subjects(dept, H.worksIn))
        worker_classes = [c for c in self._target_classes(matches, norm)
                          if self.onto.is_subclass(c, H.HealthcareWorker)]
        target = self._most_specific_class(worker_classes) if worker_classes else None
        if target:
            workers = [w for w in workers if self.onto.instance_of(w, target)]
        if not workers:
            return None
        return self._answer(
            f"{self._plural(self.onto.label(target)) if target else 'Healthcare workers'} in **{self.onto.label(dept)}**: " +
            self._join(self._labels(workers)) + ".",
            "doctors_in_department", sparql=f"SELECT ?w WHERE {{ ?w h:worksIn h:{self.onto.local(dept)} }}",
            evidence=[(w, H.worksIn, dept) for w in workers], confidence=0.98)

    def _q_workers_in_hospital(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        inds = self._inds(matches)
        if not inds or not re.search(r"\b(hospital)\b", norm):
            return None
        hosp = inds[0]
        if not self.onto.instance_of(hosp, H.Hospital):
            return None
        rows = self.onto.select(
            "SELECT DISTINCT ?w ?d WHERE { ?d h:partOf h:" + self.onto.local(hosp) +
            " . ?w h:worksIn ?d }")
        pairs = [(r["w"], r["d"]) for r in rows if isinstance(r["w"], URIRef) and isinstance(r["d"], URIRef)]
        workers = sorted({w for w, _ in pairs}, key=lambda u: self.onto.label(u))
        worker_classes = [c for c in self._target_classes(matches, norm)
                          if self.onto.is_subclass(c, H.HealthcareWorker)]
        target = self._most_specific_class(worker_classes) if worker_classes else None
        if target:
            workers = [w for w in workers if self.onto.instance_of(w, target)]
        if not workers:
            return None
        return self._answer(
            f"{self._plural(self.onto.label(target)) if target else 'Healthcare workers'} whose department is part of "
            f"**{self.onto.label(hosp)}**: " + self._join(self._labels(workers)) + ".",
            "workers_in_hospital",
            sparql="SELECT DISTINCT ?w WHERE { ?d h:partOf h:" + self.onto.local(hosp) + " . ?w h:worksIn ?d }",
            evidence=[(w, H.worksIn, d) for w, d in pairs], confidence=0.97)

    def _q_comorbidity_count(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        if not re.search(r"\b(more than|at least|two or more|multiple|comorbid)\b", norm):
            return None
        if not re.search(r"\b(patients?|diseases?|conditions?)\b", norm):
            return None
        if not re.search(r"\b(how many|which|list|who)\b", norm):
            return None
        m = re.search(r"(more than|at least)\s+(\d+)", norm)
        n = int(m.group(2)) if m else 2
        rows = self.onto.select(
            f"SELECT ?p (COUNT(DISTINCT ?d) AS ?n) WHERE {{ ?p h:diagnosedWith ?d }} "
            f"GROUP BY ?p HAVING (COUNT(DISTINCT ?d) >= {n})")
        patients = [r["p"] for r in rows if isinstance(r["p"], URIRef)]
        if not patients:
            return self._answer(f"No patients have {n} or more distinct recorded diseases.",
                                "comorbidity_count", confidence=0.95)
        return self._answer(
            f"Patients with **{n} or more** distinct recorded diseases: " +
            self._join([f"{self.onto.label(p)} ({int(r['n'])})" for p, r in zip(patients, rows)]) + ".",
            "comorbidity_count",
            sparql=f"SELECT ?p (COUNT(DISTINCT ?d) AS ?n) WHERE {{ ?p h:diagnosedWith ?d }} GROUP BY ?p HAVING (COUNT(DISTINCT ?d) >= {n})",
            confidence=0.98)

    def _q_yes_no(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        if not q.strip().endswith("?"):
            return None
        if not re.match(r"^(is|are|does|do|has|have|was|were)\b", norm):
            return None
        inds = self._inds(matches)
        classes = self._classes(matches)
        if len(inds) >= 2:
            a, b = inds[0], inds[1]
            # does A have relation B?
            for prop in self.onto.object_properties:
                if (a, prop.uri, b) in self.onto.graph or (b, prop.uri, a) in self.onto.graph:
                    label = self.onto.label(prop.uri)
                    return self._answer(
                        f"**Yes.** {self.onto.label(a)} and {self.onto.label(b)} are linked by **{label}**.",
                        "yes_no", sparql=f"ASK {{ h:{self.onto.local(a)} h:{self.onto.local(prop.uri)} h:{self.onto.local(b)} }}",
                        evidence=[(a, prop.uri, b)], confidence=0.95)
            return self._answer(
                f"**No.** No direct relationship between {self.onto.label(a)} and {self.onto.label(b)} is recorded.",
                "yes_no", ok=False, confidence=0.9)
        if inds and classes:
            ind, cls = inds[0], classes[0]
            if self._instance_of_effective(ind, cls):
                return self._answer(f"**Yes.** {self.onto.label(ind)} is a {self.onto.label(cls)}.",
                                    "yes_no", confidence=0.98)
            return self._answer(f"**No.** {self.onto.label(ind)} is not a {self.onto.label(cls)}.",
                                "yes_no", ok=False, confidence=0.95)
        return None

    def _q_instances(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        if not re.search(r"\b(list|show|who are|which are|what are|name all)\b", norm) and \
                not re.search(r"\bwhich\b.*\bare\b", norm):
            return None
        classes = self._classes(matches)
        if not classes or self._inds(matches):
            return None
        cls = self._most_specific_class(classes)
        inds = self.onto.instances_of(cls)
        inferred = []
        if not inds:
            inferred = self._inferred_instances(cls)
            inds = inferred
        if not inds:
            return self._answer(f"No individuals are recorded for {self.onto.label(cls)}.",
                                "instances", confidence=0.95)
        title = f"**{self.onto.label(cls)}** individuals ({len(inds)})"
        if inferred:
            title += " — inferred by the HermiT reasoner"
        lines = [title + ":"]
        for i in inds:
            lines.append(f"- {self.onto.label(i)} (`{self.onto.local(i)}`)")
        return self._answer("\n".join(lines), "instances", confidence=1.0 if not inferred else 0.95)

    def _q_class_description(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        classes = self._classes(matches)
        if not classes or self._inds(matches):
            return None
        if not re.search(r"\b(what is|what are|define|describe|tell me about|explain)\b", norm):
            return None
        cls = classes[0]
        info = self.onto.classes[cls]
        lines = [f"**{info.label}**"]
        if info.comment:
            lines.append(info.comment)
        supers = self.onto.direct_superclasses(cls)
        if supers:
            lines.append(f"- Subclass of: {self._join(self._labels(supers))}")
        subs = self.onto.direct_subclasses(cls)
        if subs:
            lines.append(f"- Direct subclasses: {self._join(self._labels(subs))}")
        n = self.onto.count_instances(cls)
        examples = self.onto.instances_of(cls)[:5]
        lines.append(f"- Individuals: {n}" + (f" (e.g. {self._join(self._labels(examples))})" if examples else ""))
        # properties whose domain is this class
        props = [p for p in self.onto.object_properties.values() if cls in p.domain]
        if props:
            lines.append("- Object properties: " + self._join(sorted(p.label for p in props)))
        return self._answer("\n".join(lines), "class_description", confidence=0.98)

    def _q_individual_description(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        inds = self._inds(matches)
        if not inds:
            return None
        if not re.search(r"\b(who|what|tell|describe|about|information)\b", norm):
            return None
        ind = inds[0]
        return self._describe_individual(ind)

    def _describe_individual(self, ind: URIRef) -> Answer:
        info = self.onto.individuals[ind]
        types = self.onto.types_of(ind)
        type_labels = self._join([self._type_label(t) for t in types])
        lines = [f"**{info.label}** (`{self.onto.local(ind)}`) — {type_labels}"]
        if self.onto.instance_of(ind, H.Patient):
            for p, label in [(H.patientId, "Patient ID"), (H.age, "Age"), (H.gender, "Gender"),
                             (H.bloodGroup, "Blood group"), (H.phone, "Phone")]:
                vals = self.onto.values(ind, p)
                if vals:
                    lines.append(f"- {label}: {self.onto.fmt_value(vals[0])}")
            diseases = self.onto.objects(ind, H.diagnosedWith)
            if diseases:
                lines.append("- Diagnoses: " + self._join(self._labels(diseases)))
            symptoms = self.onto.objects(ind, H.hasSymptom)
            if symptoms:
                lines.append("- Symptoms: " + self._join(self._labels(symptoms)))
            docs = self.onto.objects(ind, H.treatedBy)
            if docs:
                lines.append("- Treated by: " + self._join(self._labels(docs)))
            plans = self.onto.objects(ind, H.hasInsurance)
            if plans:
                lines.append("- Insurance: " + self._join(self._labels(plans)))
            appts = self.onto.objects(ind, H.hasAppointment)
            if appts:
                lines.append(f"- Appointments: {len(appts)}")
            meds = list(self.onto.subjects(ind, H.prescribedFor))
            if meds:
                lines.append("- Medications: " + self._join(self._labels(meds)))
        elif self.onto.instance_of(ind, H.Doctor):
            for p, label in [(H.doctorId, "Doctor ID"), (H.specialty, "Specialty"),
                             (H.licenseNumber, "License"), (H.phone, "Phone"), (H.email, "Email")]:
                vals = self.onto.values(ind, p)
                if vals:
                    lines.append(f"- {label}: {self.onto.fmt_value(vals[0])}")
            depts = self.onto.objects(ind, H.worksIn)
            if depts:
                hospitals = []
                for d in depts:
                    hospitals += list(self.onto.graph.objects(d, H.partOf))
                lines.append("- Works in: " + self._join(self._labels(depts)) +
                             (f" ({self._join(self._labels(hospitals))})" if hospitals else ""))
            patients = self.onto.subjects(ind, H.treatedBy)
            if patients:
                lines.append("- Treats patients: " + self._join(self._labels(patients)))
            diseases = self.onto.objects(ind, H.treatsDisease)
            if diseases:
                lines.append("- Treats diseases: " + self._join(self._labels(diseases)))
            if any(self.onto.graph.objects(ind, H.headOf)):
                lines.append("- Head of: " + self._join(self._labels(self.onto.objects(ind, H.headOf))))
        elif self.onto.instance_of(ind, H.Disease):
            systems = self.onto.objects(ind, H.hasAffectedSystem)
            if systems:
                lines.append("- Affects: " + self._join(self._labels(systems)))
            symptoms = self.onto.objects(ind, H.causes)
            if symptoms:
                lines.append("- Symptoms caused: " + self._join(self._labels(symptoms)))
            treatments = self.onto.objects(ind, H.treatedWith)
            if treatments:
                lines.append("- Treated with: " + self._join(self._labels(treatments)))
            patients = self.onto.subjects(ind, H.diagnosedWith)
            if patients:
                lines.append("- Patients: " + self._join(self._labels(patients)))
        elif self.onto.instance_of(ind, H.Medication):
            for p, label in [(H.dosage, "Dosage"), (H.frequency, "Frequency"), (H.cost, "Cost")]:
                vals = self.onto.values(ind, p)
                if vals:
                    lines.append(f"- {label}: {self.onto.fmt_value(vals[0])}")
            patients = self.onto.subjects(ind, H.prescribedFor)
            if patients:
                lines.append("- Prescribed for: " + self._join(self._labels(patients)))
            doctors = self.onto.subjects(ind, H.prescribedBy)
            if doctors:
                lines.append("- Prescribed by: " + self._join(self._labels(doctors)))
            interactions = set(self.onto.objects(ind, H.interactsWith)) | set(self.onto.subjects(ind, H.interactsWith))
            if interactions:
                lines.append("- Interactions: " + self._join(self._labels(interactions)))
        elif self.onto.instance_of(ind, H.Appointment):
            for p, label in [(H.appointmentDate, "Date"), (H.appointmentTime, "Time"),
                             (H.reason, "Reason"), (H.status, "Status"), (H.cost, "Cost")]:
                vals = self.onto.values(ind, p)
                if vals:
                    lines.append(f"- {label}: {self.onto.fmt_value(vals[0])}")
            pat = self.onto.objects(ind, H.forPatient)
            doc = self.onto.objects(ind, H.withDoctor)
            if pat:
                lines.append("- Patient: " + self._join(self._labels(pat)))
            if doc:
                lines.append("- Doctor: " + self._join(self._labels(doc)))
        elif self.onto.instance_of(ind, H.Department):
            hosp = []
            for d in self.onto.objects(ind, H.partOf):
                hosp += list(self.onto.graph.objects(d, H.partOf)) or [d]
            if hosp:
                lines.append("- Part of: " + self._join(self._labels(hosp)))
            workers = self.onto.subjects(ind, H.worksIn)
            if workers:
                lines.append("- Staff: " + self._join(self._labels(workers)))
            heads = self.onto.subjects(ind, H.headOf)
            if heads:
                lines.append("- Head: " + self._join(self._labels(heads)))
        elif self.onto.instance_of(ind, H.Hospital):
            depts = [d for d in self.onto.subjects(ind, H.partOf)]
            if depts:
                lines.append("- Departments: " + self._join(self._labels(depts)))
            vals = self.onto.values(ind, H.city)
            if vals:
                lines.append("- City: " + self.onto.fmt_value(vals[0]))
        elif self.onto.instance_of(ind, H.InsurancePlan):
            for p, label in [(H.policyNumber, "Policy"), (H.coveragePercentage, "Coverage"),
                             (H.monthlyPremium, "Monthly premium")]:
                vals = self.onto.values(ind, p)
                if vals:
                    lines.append(f"- {label}: {self.onto.fmt_value(vals[0])}")
            diseases = self.onto.objects(ind, H.coversDisease)
            if diseases:
                lines.append("- Covered diseases: " + self._join(self._labels(diseases)))
            patients = self.onto.subjects(ind, H.hasInsurance)
            if patients:
                lines.append("- Insured patients: " + self._join(self._labels(patients)))
        elif self.onto.instance_of(ind, H.Symptom):
            vals = self.onto.values(ind, H.severity)
            if vals:
                lines.append(f"- Severity: {self.onto.fmt_value(vals[0])}/10")
            diseases = self.onto.subjects(ind, H.causes)
            if diseases:
                lines.append("- Caused by: " + self._join(self._labels(diseases)))
            patients = self.onto.subjects(ind, H.hasSymptom)
            if patients:
                lines.append("- Patients with this symptom: " + self._join(self._labels(patients)))

        # Reasoner insight (optional, computed by HermiT)
        if self.reasoner is not None:
            ok, err = self.reasoner.run()
            if ok:
                inferred = [t for t in self.reasoner.inferred_types(str(ind))
                            if t not in {self.onto.local(t) for t in types}]
                if inferred:
                    labels = []
                    for t in inferred:
                        uri = URIRef(str(H) + t)
                        labels.append(self.onto.label(uri) if uri in self.onto.classes else t)
                    lines.append("- Inferred by HermiT: " + self._join(labels))

        query = f"SELECT ?p ?o WHERE {{ h:{self.onto.local(ind)} ?p ?o }}"
        ev = [(ind, p, o) for p, o in self.onto.graph.predicate_objects(ind)]
        return self._answer("\n".join(lines), "individual_description", sparql=query,
                            evidence=ev, confidence=0.99,
                            entities=[info.label])

    # ------------------------------------------------------------- generic
    def _select_property(self, subject: URIRef, target: URIRef,
                         text: str) -> Optional[tuple[URIRef, bool]]:
        """Pick the object property that best connects *subject* to *target*."""
        norm = normalize(text)
        tokens = set(norm.split()) - STOPWORDS
        best = None
        best_score = 0
        for p in self.onto.object_properties.values():
            score = 0
            dom = p.domain[0] if p.domain else None
            rng = p.range[0] if p.range else None
            forward = False
            if dom and rng:
                if self.onto.instance_of(subject, dom) and self._class_fits(target, rng):
                    forward = True
                    score += 14
                elif self.onto.instance_of(subject, rng) and self._class_fits(target, dom):
                    forward = False
                    score += 12
            else:
                score += 1
            label_tokens = set(normalize(p.label).split()) - STOPWORDS
            overlap = label_tokens & tokens
            score += 3 * len(overlap)
            for kw, boosts in KEYWORD_BOOSTS.items():
                if kw in norm:
                    score += boosts.get(self.onto.local(p.uri), 0)
            if score > best_score:
                best_score = score
                best = (p.uri, not forward)
        if best and best_score >= 8:
            return best
        return None

    def _class_fits(self, cls: URIRef, superclass: URIRef) -> bool:
        if cls == superclass:
            return True
        return self.onto.is_subclass(cls, superclass)

    def _relation_values(self, subject: URIRef, prop: URIRef, inverse: bool) -> list:
        if inverse:
            return list(self.onto.subjects(subject, prop))
        return list(self.onto.objects(subject, prop))

    def _relation_values_auto(self, subject: URIRef, target: URIRef, prop: URIRef) -> tuple[list, Optional[URIRef], bool]:
        """Return values linked to *subject* by *prop*, trying the property's inverse.

        OWL object properties are often asserted in only one direction; this
        resolves the direction that actually exists in the graph.
        """
        info = self.onto.object_properties.get(prop)
        candidates: list[tuple[URIRef, bool]] = [(prop, False), (prop, True)]
        if info and info.inverse:
            candidates += [(info.inverse, False), (info.inverse, True)]
        for p, inv in candidates:
            vals = self._relation_values(subject, p, inv)
            good = [v for v in vals if self.onto.instance_of(v, target)]
            if good:
                return good, p, inv
        return [], prop, False

    def _instance_of_effective(self, ind: URIRef, cls: URIRef) -> bool:
        if self.onto.instance_of(ind, cls):
            return True
        if self.reasoner is not None and self.reasoner.run()[0]:
            inferred = self.reasoner.inferred_types(str(ind))
            return self.onto.local(cls) in inferred
        return False

    def _q_generic_relation(self, q: str, norm: str, matches: list[EntityMatch]) -> Optional[Answer]:
        inds = self._inds(matches)
        classes = self._target_classes(matches, norm)
        if not inds or not classes:
            return None
        subject = inds[0]
        target = classes[-1]
        chosen = self._select_property(subject, target, q)
        if chosen:
            prop, inverse = chosen
            vals, used, used_inv = self._relation_values_auto(subject, target, prop)
            if vals:
                query = (f"SELECT ?o WHERE {{ h:{self.onto.local(subject)} h:{self.onto.local(used)} ?o }}" if not used_inv
                         else f"SELECT ?s WHERE {{ ?s h:{self.onto.local(used)} h:{self.onto.local(subject)} }}")
                ev = [(subject, used, v) for v in vals] if not used_inv else [(v, used, subject) for v in vals]
                return self._answer(
                    f"**{self.onto.label(subject)}** -> {self.onto.label(used)} -> "
                    + self._join(self._labels(vals)) + ".",
                    "generic_relation", sparql=query, evidence=ev, confidence=0.9)
        # BFS over all requested classes, pick the best path
        best: Optional[tuple[PathResult, URIRef]] = None
        for target in classes:
            for path in self.onto.find_paths(subject, target, max_depth=3):
                key = (path.mentioned, -len(path.predicates))
                if best is None or key > (best[0].mentioned, -len(best[0].predicates)):
                    best = (path, target)
        if best:
            path, target = best
            vals = [n for n in path.nodes[1:] if self.onto.instance_of(n, target)]
            if vals:
                return self._answer(
                    f"**{self.onto.label(subject)}** is connected to " + self._join(self._labels(vals)) +
                    f" via: {path.describe(self.onto)}.",
                    "generic_relation", sparql=self.onto.property_path_query(subject, target) or "",
                    confidence=0.85)
        return None

    def _paths_between(self, a: URIRef, b: URIRef, max_depth: int = 3) -> list[PathResult]:
        """Undirected BFS between two individuals, returning paths."""
        results: list[PathResult] = []
        queue: list[tuple[URIRef, list[URIRef], list[URIRef], list[bool]]] = [(a, [a], [], [])]
        seen = {a}
        while queue:
            node, nodes, preds, revs = queue.pop(0)
            if len(preds) >= max_depth:
                continue
            for nxt, prop, forward in self.onto._adj.get(node, []):
                if nxt in seen:
                    continue
                if nxt == b:
                    results.append(PathResult(nodes + [b], preds + [prop], revs + [not forward], 0))
                seen.add(nxt)
                queue.append((nxt, nodes + [nxt], preds + [prop], revs + [not forward]))
        results.sort(key=lambda p: len(p.predicates))
        return results