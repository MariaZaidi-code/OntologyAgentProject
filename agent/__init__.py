"""Hospital Management Ontology agent package."""
from .ontology import H, OntologyService, ReasonerService
from .engine import Answer, OntologyAgent

__all__ = ["H", "OntologyService", "ReasonerService", "Answer", "OntologyAgent"]