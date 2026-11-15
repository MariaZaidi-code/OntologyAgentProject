"""Ontology access layer for the Hospital Management Ontology.

Wraps an OWL file with:
  * rdflib graph parsing + SPARQL helpers
  * label / alias index for natural-language entity linking
  * class-hierarchy helpers (subclass closure, instances, counts)
  * object-property traversal (forward, inverse, transitive closure, BFS paths)
  * optional HermiT reasoning through owlready2
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS

H = Namespace("http://example.org/hospital#")

# Words that carry no discriminative power when matching properties.
STOPWORDS = {
    "a", "an", "the", "of", "for", "to", "in", "on", "at", "by", "with",
    "is", "are", "was", "were", "do", "does", "did", "has", "have", "had",
    "which", "who", "whom", "what", "when", "where", "how", "many", "much",
    "all", "any", "list", "show", "give", "tell", "me", "about", "please",
}


def normalize(text: str) -> str:
    """Lower-case, strip punctuation and collapse whitespace."""
    text = text.lower().replace("\u2019", "'")
    text = re.sub(r"\b\w+'s\b", lambda m: m.group(0)[:-2], text)  # John's -> John
    text = re.sub(r"[^a-z0-9+]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def humanize_local(local: str) -> str:
    """p001 -> p001, Type2Diabetes -> type2 diabetes, dept_cardio -> dept cardio."""
    local = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", local)
    return local.replace("_", " ").strip()


@dataclass
class ClassInfo:
    uri: URIRef
    label: str
    comment: str = ""
    parents: list[URIRef] = field(default_factory=list)


@dataclass
class PropertyInfo:
    uri: URIRef
    label: str
    kind: str  # "object" | "data"
    domain: list[URIRef] = field(default_factory=list)
    range: list[URIRef] = field(default_factory=list)
    inverse: Optional[URIRef] = None
    characteristics: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)


@dataclass
class IndividualInfo:
    uri: URIRef
    label: str
    types: list[URIRef] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)


@dataclass
class EntityMatch:
    kind: str  # "class" | "individual" | "object_property" | "data_property"
    uri: URIRef
    label: str
    start: int
    end: int


@dataclass
class PathResult:
    nodes: list[URIRef]
    predicates: list[URIRef]
    reversed: list[bool]
    mentioned: int

    def describe(self, svc: "OntologyService") -> str:
        parts = [svc.label(self.nodes[0])]
        for pred, rev, node in zip(self.predicates, self.reversed, self.nodes[1:]):
            label = svc.label(pred)
            if rev:
                info = svc.object_properties.get(pred)
                inverse = info.inverse if info else None
                if inverse and inverse in svc.object_properties:
                    label = svc.label(inverse)
                else:
                    label = "inverse of " + label
            parts.append(f"[{label}] {svc.label(node)}")
        return " -> ".join(parts)


class OntologyService:
    """Loads the OWL file and answers structural / instance questions."""

    def __init__(self, owl_path: str | Path):
        self.owl_path = Path(owl_path)
        if not self.owl_path.exists():
            raise FileNotFoundError(f"Ontology file not found: {self.owl_path}")

        self.graph = Graph()
        fmt = "xml" if self.owl_path.suffix.lower() in {".owl", ".rdf", ".xml"} else "turtle"
        self.graph.parse(str(self.owl_path), format=fmt)
        self.graph.bind("h", H)
        self.graph.bind("owl", OWL)
        self.graph.bind("rdfs", RDFS)

        self.classes: dict[URIRef, ClassInfo] = {}
        self.object_properties: dict[URIRef, PropertyInfo] = {}
        self.data_properties: dict[URIRef, PropertyInfo] = {}
        self.individuals: dict[URIRef, IndividualInfo] = {}
        self._alias_index: list[tuple[str, str, URIRef, int]] = []
        self._adj: dict[URIRef, list[tuple[URIRef, URIRef, bool]]] = {}
        self._build()

    # ------------------------------------------------------------------ build
    def _label(self, uri: URIRef) -> str:
        labels = list(self.graph.objects(uri, RDFS.label))
        for lab in labels:
            if getattr(lab, "language", None) in (None, "en"):
                return str(lab)
        if labels:
            return str(labels[0])
        return humanize_local(str(uri).split("#")[-1])

    def _comment(self, uri: URIRef) -> str:
        for com in self.graph.objects(uri, RDFS.comment):
            return str(com)
        return ""

    def _build(self) -> None:
        # Classes
        for cls in self.graph.subjects(RDF.type, OWL.Class):
            if not isinstance(cls, URIRef):
                continue
            parents = [p for p in self.graph.objects(cls, RDFS.subClassOf) if isinstance(p, URIRef)]
            info = ClassInfo(cls, self._label(cls), "", parents)
            info.comment = self._comment(cls)
            self.classes[cls] = info
            self._add_aliases("class", cls, info.label)
            # plural alias
            self._alias_index.append((normalize(info.label) + "s", "class", cls, 0))

        # Object properties
        for prop in self.graph.subjects(RDF.type, OWL.ObjectProperty):
            if not isinstance(prop, URIRef):
                continue
            info = PropertyInfo(
                uri=prop,
                label=self._label(prop),
                kind="object",
                domain=[d for d in self.graph.objects(prop, RDFS.domain) if isinstance(d, URIRef)],
                range=[r for r in self.graph.objects(prop, RDFS.range) if isinstance(r, URIRef)],
                inverse=next((i for i in self.graph.objects(prop, OWL.inverseOf) if isinstance(i, URIRef)), None),
            )
            info.characteristics = [
                str(c).split("#")[-1]
                for c in self.graph.objects(prop, RDF.type)
                if str(c).startswith(str(OWL)) and str(c).split("#")[-1] in
                {"SymmetricProperty", "TransitiveProperty", "FunctionalProperty",
                 "InverseFunctionalProperty", "IrreflexiveProperty", "AsymmetricProperty"}
            ]
            info.aliases = self._property_aliases(prop, info)
            self.object_properties[prop] = info
            for alias in {info.label, *info.aliases}:
                self._alias_index.append((normalize(alias), "object_property", prop, 1))

        # Data properties
        for prop in self.graph.subjects(RDF.type, OWL.DatatypeProperty):
            if not isinstance(prop, URIRef):
                continue
            info = PropertyInfo(
                uri=prop,
                label=self._label(prop),
                kind="data",
                domain=[d for d in self.graph.objects(prop, RDFS.domain) if isinstance(d, URIRef)],
                range=[r for r in self.graph.objects(prop, RDFS.range) if isinstance(r, URIRef)],
            )
            info.characteristics = [
                str(c).split("#")[-1]
                for c in self.graph.objects(prop, RDF.type)
                if str(c).startswith(str(OWL)) and str(c).split("#")[-1] == "FunctionalProperty"
            ]
            info.aliases = self._property_aliases(prop, info)
            self.data_properties[prop] = info
            for alias in {info.label, *info.aliases}:
                self._alias_index.append((normalize(alias), "data_property", prop, 1))

        # Individuals
        for ind in self.graph.subjects(RDF.type, OWL.NamedIndividual):
            if not isinstance(ind, URIRef):
                continue
            label = self._label(ind)
            types = [t for t in self.graph.objects(ind, RDF.type)
                     if isinstance(t, URIRef) and t != OWL.NamedIndividual]
            info = IndividualInfo(ind, label, types)
            self.individuals[ind] = info
            self._add_aliases("individual", ind, label)
            # "Dr. Patel" style surname aliases (doctors only, to avoid ambiguity)
            if label.lower().startswith("dr"):
                parts = [p for p in label.replace("Dr.", "").split() if p]
                if parts:
                    surname = parts[-1]
                    self._alias_index.append((normalize(surname), "individual", ind, 3))
                    self._alias_index.append((normalize("dr " + surname), "individual", ind, 4))
            # identifier aliases (patientId / doctorId / employeeId / policyNumber)
            for idp in (H.patientId, H.doctorId, H.employeeId, H.policyNumber):
                for val in self.graph.objects(ind, idp):
                    info.aliases.append(str(val))
                    self._alias_index.append((normalize(str(val)), "individual", ind, 5))

        # adjacency for BFS (object properties only)
        for s, p, o in self.graph:
            if p in self.object_properties and isinstance(s, URIRef) and isinstance(o, URIRef):
                self._adj.setdefault(s, []).append((o, p, True))
                self._adj.setdefault(o, []).append((s, p, False))

    def _add_aliases(self, kind: str, uri: URIRef, label: str) -> None:
        local = str(uri).split("#")[-1]
        self._alias_index.append((normalize(label), kind, uri, 2))
        self._alias_index.append((normalize(humanize_local(local)), kind, uri, 0))
        self._alias_index.append((normalize(local), kind, uri, 0))

    def _property_aliases(self, prop: URIRef, info: PropertyInfo) -> list[str]:
        """Human phrasings for each property (used by the NL matcher)."""
        table = {
            "hasSymptom": ["symptoms of", "symptoms", "has symptom"],
            "diagnosedWith": ["diagnosed with", "diseases of", "conditions of", "diagnosis"],
            "causes": ["causes", "caused by"],
            "hasAffectedSystem": ["affected system", "affects", "affect"],
            "treatedBy": ["treated by", "doctor of", "treating doctor", "physician of"],
            "treatsPatient": ["treats", "treats patient", "patients of"],
            "treatsDisease": ["treats", "treats disease"],
            "worksIn": ["works in", "works at", "work in", "work at", "department of", "works"],
            "headOf": ["head of", "heads", "director of"],
            "affiliatedWith": ["affiliated with", "affiliation"],
            "partOf": ["part of", "belongs to", "located in"],
            "forPatient": ["for patient", "patient of"],
            "withDoctor": ["with doctor", "doctor of"],
            "hasAppointment": ["appointments", "has appointment", "appointment of"],
            "hasScheduledAppointment": ["scheduled appointments", "appointments"],
            "hasMedicalRecord": ["medical record", "medical records"],
            "recordsDiagnosis": ["records diagnosis", "recorded diagnosis"],
            "hasPrescription": ["prescription", "prescriptions", "medication of"],
            "treatedWith": ["treated with", "treatment for"],
            "prescribedFor": ["prescribed for", "prescribed to"],
            "prescribedBy": ["prescribed by", "prescriber"],
            "interactsWith": ["interacts with", "interactions with", "interaction with", "drug interactions"],
            "allergicTo": ["allergic to", "allergy to"],
            "hasInsurance": ["insurance", "insured by", "insurance plan"],
            "coversDisease": ["covers", "covered by", "coverage for"],
            "affectsPatient": ["affects patient", "patients of"],
            "indicatedBy": ["indicated by"],
        }
        aliases = list(table.get(str(prop).split("#")[-1], []))
        aliases.append(humanize_local(str(prop).split("#")[-1]))
        return aliases

    # --------------------------------------------------------------- matching
    def match_entities(self, text: str) -> list[EntityMatch]:
        """Longest-match, non-overlapping entity linking over the label index."""
        norm = normalize(text)
        candidates: list[tuple[int, int, str, URIRef, int]] = []
        for alias, kind, uri, prio in self._alias_index:
            if not alias or len(alias) < 2:
                continue
            pattern = r"(?<![a-z0-9])" + re.escape(alias).replace(r"\ ", r"\s+") + r"(?![a-z0-9])"
            for m in re.finditer(pattern, norm):
                candidates.append((m.start(), m.end(), kind, uri, prio))

        # Longest / highest-priority first, then greedily accept non-overlapping.
        candidates.sort(key=lambda c: (-(c[1] - c[0]), -c[4], c[0]))
        accepted: list[EntityMatch] = []
        occupied: list[tuple[int, int]] = []
        for start, end, kind, uri, _ in candidates:
            if any(start < e and end > s for s, e in occupied):
                continue
            occupied.append((start, end))
            info = self._entity_info(kind, uri)
            accepted.append(EntityMatch(kind, uri, info, start, end))
        accepted.sort(key=lambda m: m.start)
        return accepted

    def _entity_info(self, kind: str, uri: URIRef) -> str:
        if kind == "class" and uri in self.classes:
            return self.classes[uri].label
        if kind == "individual" and uri in self.individuals:
            return self.individuals[uri].label
        if uri in self.object_properties:
            return self.object_properties[uri].label
        if uri in self.data_properties:
            return self.data_properties[uri].label
        return self.label(uri)

    def find_data_property(self, text: str) -> Optional[tuple[URIRef, str, int]]:
        """Find the data property mentioned in *text* (longest alias wins)."""
        norm = normalize(text)
        best: Optional[tuple[URIRef, str, int]] = None
        for alias, kind, uri, _ in self._alias_index:
            if kind != "data_property" or not alias:
                continue
            pattern = r"(?<![a-z0-9])" + re.escape(alias).replace(r"\ ", r"\s+") + r"(?![a-z0-9])"
            m = re.search(pattern, norm)
            if m and (best is None or len(alias) > len(best[1])):
                best = (uri, alias, m.start())
        if best is None and re.search(r"\bhow old\b", norm):
            best = (H.age, "age", norm.find("old"))
        return best

    # --------------------------------------------------------------- SPARQL
    def _ns(self) -> dict:
        return {"h": H, "rdf": RDF, "rdfs": RDFS, "owl": OWL}

    def select(self, query: str) -> list[dict]:
        rows = []
        for row in self.graph.query(query, initNs=self._ns()):
            rows.append({str(k): v for k, v in row.asdict().items()})
        return rows

    def ask(self, query: str) -> bool:
        return bool(self.graph.query(query, initNs=self._ns()).askAnswer)

    def local(self, uri: URIRef) -> str:
        return str(uri).split("#")[-1]

    # --------------------------------------------------------------- basics
    def label(self, uri: URIRef) -> str:
        if uri in self.classes:
            return self.classes[uri].label
        if uri in self.individuals:
            return self.individuals[uri].label
        if uri in self.object_properties:
            return self.object_properties[uri].label
        if uri in self.data_properties:
            return self.data_properties[uri].label
        return self._label(uri)

    def comment(self, uri: URIRef) -> str:
        return self._comment(uri)

    def types_of(self, uri: URIRef) -> list[URIRef]:
        if uri not in self.individuals:
            return []
        return self.individuals[uri].types

    def named_classes(self) -> list[URIRef]:
        return sorted(self.classes, key=lambda u: self.label(u).lower())

    def direct_subclasses(self, uri: URIRef) -> list[URIRef]:
        return sorted(
            {s for s in self.graph.subjects(RDFS.subClassOf, uri) if isinstance(s, URIRef)},
            key=lambda u: self.label(u).lower(),
        )

    def all_subclasses(self, uri: URIRef) -> list[URIRef]:
        rows = self.select(
            f"SELECT DISTINCT ?c WHERE {{ ?c rdfs:subClassOf+ h:{self.local(uri)} }}")
        return sorted({row["c"] for row in rows if isinstance(row["c"], URIRef)}, key=lambda u: self.label(u).lower())

    def direct_superclasses(self, uri: URIRef) -> list[URIRef]:
        return sorted(
            {s for s in self.graph.objects(uri, RDFS.subClassOf) if isinstance(s, URIRef)},
            key=lambda u: self.label(u).lower(),
        )

    def is_subclass(self, child: URIRef, parent: URIRef) -> bool:
        return self.ask(
            f"ASK {{ h:{self.local(child)} rdfs:subClassOf* h:{self.local(parent)} }}")

    def instance_of(self, ind: URIRef, cls: URIRef) -> bool:
        return self.ask(
            f"ASK {{ h:{self.local(ind)} rdf:type/rdfs:subClassOf* h:{self.local(cls)} }}")

    def instances_of(self, cls: URIRef, direct: bool = False) -> list[URIRef]:
        path = f"h:{self.local(cls)}" if direct else f"h:{self.local(cls)}"
        pattern = f"?i rdf:type/rdfs:subClassOf* {path}" if not direct else f"?i rdf:type {path}"
        rows = self.select(f"SELECT DISTINCT ?i WHERE {{ {pattern} }}")
        return sorted({r["i"] for r in rows if isinstance(r["i"], URIRef)}, key=lambda u: self.label(u).lower())

    def count_instances(self, cls: URIRef, direct: bool = False) -> int:
        pattern = f"?i rdf:type {self.local(cls)}" if direct else f"?i rdf:type/rdfs:subClassOf* h:{self.local(cls)}"
        rows = self.select(f"SELECT (COUNT(DISTINCT ?i) AS ?n) WHERE {{ {pattern} }}")
        return int(rows[0]["n"]) if rows else 0

    def objects(self, subj: URIRef, prop: URIRef) -> list[URIRef | Literal]:
        return list(self.graph.objects(subj, prop))

    def subjects(self, obj: URIRef, prop: URIRef) -> list[URIRef]:
        return list(self.graph.subjects(prop, obj))

    def values(self, subj: URIRef, prop: URIRef) -> list[Literal]:
        return [o for o in self.graph.objects(subj, prop) if isinstance(o, Literal)]

    def fmt_value(self, val) -> str:
        if isinstance(val, Literal):
            text = str(val)
            if getattr(val, "datatype", None) is not None and "date" in str(val.datatype):
                return text.split("T")[0]
            if isinstance(val.toPython(), float):
                return f"{val.toPython():g}"
            return text
        return self.label(val)

    # --------------------------------------------------------------- BFS
    def find_paths(self, start: URIRef, target: URIRef, max_depth: int = 3,
                   preferred: Optional[Iterable[URIRef]] = None,
                   limit: int = 8) -> list[PathResult]:
        """Shortest object-property paths from *start* to any instance of *target*."""
        preferred = list(preferred or [])
        preferred_tokens = set()
        for p in preferred:
            preferred_tokens.update(normalize(self.label(p)).split())

        results: list[PathResult] = []
        # queue: (node, nodes, preds, revs, mentioned)
        queue: list[tuple[URIRef, list[URIRef], list[URIRef], list[bool], int]] = [
            (start, [start], [], [], 0)
        ]
        seen: set[URIRef] = {start}
        while queue and len(results) < 40:
            node, nodes, preds, revs, mentioned = queue.pop(0)
            if len(preds) >= max_depth:
                continue
            for nxt, prop, is_forward in self._adj.get(node, []):
                if nxt in seen:
                    continue
                toks = set(normalize(self.label(prop)).split()) - STOPWORDS
                mention = len(toks & preferred_tokens)
                new_nodes = nodes + [nxt]
                new_preds = preds + [prop]
                new_revs = revs + [not is_forward]
                if self.instance_of(nxt, target):
                    results.append(PathResult(new_nodes, new_preds, new_revs, mentioned + mention))
                seen.add(nxt)
                queue.append((nxt, new_nodes, new_preds, new_revs, mentioned + mention))

        results.sort(key=lambda p: (-p.mentioned, len(p.predicates), len(p.nodes)))
        return results[:limit]

    def property_path_query(self, start: URIRef, target: URIRef, max_depth: int = 3) -> Optional[str]:
        """Build a SPARQL property-path query for a shortest path (documentation)."""
        paths = self.find_paths(start, target, max_depth=max_depth, limit=1)
        if not paths:
            return None
        p = paths[0]
        parts = []
        for prop, rev in zip(p.predicates, p.reversed):
            name = f"h:{self.local(prop)}"
            parts.append(f"^{name}" if rev else name)
        chain = "/".join(parts)
        return (f"SELECT ?x WHERE {{ h:{self.local(start)} {chain} ?x . "
                f"?x rdf:type/rdfs:subClassOf* h:{self.local(target)} }}")

    # --------------------------------------------------------------- stats
    def stats(self) -> dict:
        return {
            "classes": len(self.classes),
            "object_properties": len(self.object_properties),
            "data_properties": len(self.data_properties),
            "individuals": len(self.individuals),
            "triples": len(self.graph),
            "patients": self.count_instances(H.Patient),
            "doctors": self.count_instances(H.Doctor),
            "diseases": self.count_instances(H.Disease),
            "medications": self.count_instances(H.Medication),
            "appointments": self.count_instances(H.Appointment),
        }

    def class_of_individual(self, ind: URIRef) -> Optional[URIRef]:
        """Most specific named asserted type (fallback to any type)."""
        types = self.types_of(ind)
        if not types:
            return None
        # prefer types that are not superclasses of other asserted types
        specific = [t for t in types if not any(t != o and self.is_subclass(o, t) for o in types)]
        specific.sort(key=lambda t: (0 if t in (H.Patient, H.Doctor, H.Nurse, H.Medication,
                                                H.Disease, H.Appointment, H.InsurancePlan) else 1,
                                     self.label(t)))
        return specific[0] if specific else types[0]

    def class_of_value(self, val: URIRef) -> Optional[URIRef]:
        if val in self.individuals:
            return self.class_of_individual(val)
        return None

    def label_of_class_path(self, uri: URIRef) -> str:
        return self.label(uri)


# --------------------------------------------------------------------- reasoner
class ReasonerService:
    """Optional HermiT reasoning via owlready2 (used for inferred-class insights)."""

    def __init__(self, owl_path: str | Path, java_home: Optional[str] = None):
        import os
        import owlready2

        if java_home:
            os.environ["JAVA_HOME"] = java_home
            os.environ["PATH"] = str(Path(java_home) / "bin") + os.pathsep + os.environ.get("PATH", "")
        owlready2.onto_path.append(str(Path(owl_path).resolve().parent))
        self.owlready2 = owlready2
        # owlready2 resolves a bare filename against onto_path (more reliable than file:// URIs on Windows)
        self.onto = owlready2.get_ontology(Path(owl_path).name).load()
        self._ran = False
        self._consistent: Optional[bool] = None
        self._error: Optional[str] = None

    def run(self) -> tuple[bool, Optional[str]]:
        if self._ran:
            return self._consistent or False, self._error
        try:
            with self.onto:
                self.owlready2.sync_reasoner_hermit(self.onto, infer_property_values=True, debug=0)
            self._consistent = True
        except Exception as exc:  # pragma: no cover - depends on local Java
            self._error = f"{type(exc).__name__}: {exc}"
            self._consistent = False
        self._ran = True
        return self._consistent, self._error

    def consistent(self) -> bool:
        ok, _ = self.run()
        return ok

    def inferred_types(self, uri: str) -> list[str]:
        """Return inferred class labels for an individual IRI."""
        ok, _ = self.run()
        if not ok:
            return []
        ind = self.onto.search_one(iri=uri)
        if ind is None:
            return []
        out = []
        for cls in ind.is_a:
            if cls is self.owlready2.Thing:
                continue
            out.append(cls.iri.split("#")[-1])
        return out

    def inconsistent_individuals(self) -> list[str]:
        ok, _ = self.run()
        if not ok:
            return []
        query = getattr(self.onto.world, "inconsistent_individuals", None)
        if query is None:  # older owlready2 releases
            return []
        return [i.iri for i in query()]