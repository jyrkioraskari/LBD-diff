from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS, PROV
from rdflib.term import Node

IGNORED_PREDICATES = frozenset({PROV.generatedAtTime})
URI_TIMESTAMP_SUFFIX = re.compile(r"p\d+$")
PROPERTY_SUFFIX = re.compile(r"_(?:property|attribute)_simple$")

CANONICAL_INSTANCE_NAMESPACE = "urn:lbd-diff:inst/"
INSTANCE_NAMESPACES = (
    "https://www.ugent.be/myAwesomeFirstBIMProject#",
    "https://lbd.example.com/",
)

OPM_PROPERTY = URIRef("https://w3id.org/opm#Property")
OPM_CURRENT_PROPERTY_STATE = URIRef("https://w3id.org/opm#CurrentPropertyState")
OPM_HAS_PROPERTY_STATE = URIRef("https://w3id.org/opm#hasPropertyState")
PROPS_NAMESPACE = "http://lbd.arch.rwth-aachen.de/props#"
SCHEMA_VALUE = URIRef("http://schema.org/value")
SMLS_UNIT = URIRef("https://w3id.org/smls/unit")


@dataclass(frozen=True)
class PredicateValue:
    predicate: Node
    value: Node


@dataclass(frozen=True)
class ResourceDiff:
    subject: Node
    added: tuple[PredicateValue, ...]
    removed: tuple[PredicateValue, ...]


@dataclass(frozen=True)
class ModelDiff:
    first_file: Path
    second_file: Path
    first_triple_count: int
    second_triple_count: int
    added_resources: tuple[ResourceDiff, ...]
    removed_resources: tuple[ResourceDiff, ...]
    changed_resources: tuple[ResourceDiff, ...]

    @property
    def has_changes(self) -> bool:
        return bool(self.added_resources or self.removed_resources or self.changed_resources)


def load_turtle(path: str | Path) -> Graph:
    graph = Graph()
    graph.parse(Path(path), format="turtle")
    return graph


def diff_turtle_files(first_path: str | Path, second_path: str | Path) -> ModelDiff:
    first_file = Path(first_path)
    second_file = Path(second_path)
    return diff_graphs(load_turtle(first_file), load_turtle(second_file), first_file, second_file)


def diff_graphs(
    first: Graph,
    second: Graph,
    first_file: str | Path = Path("first.ttl"),
    second_file: str | Path = Path("second.ttl"),
) -> ModelDiff:
    first_by_subject = _subject_map(first)
    second_by_subject = _subject_map(second)
    first_triple_count = sum(len(values) for values in first_by_subject.values())
    second_triple_count = sum(len(values) for values in second_by_subject.values())

    first_subjects = set(first_by_subject)
    second_subjects = set(second_by_subject)

    removed_subjects = first_subjects - second_subjects
    added_subjects = second_subjects - first_subjects
    common_subjects = first_subjects & second_subjects

    added_resources = tuple(
        _resource_diff(subject, added=second_by_subject[subject], removed=set())
        for subject in sorted(added_subjects, key=_sort_key)
    )
    removed_resources = tuple(
        _resource_diff(subject, added=set(), removed=first_by_subject[subject])
        for subject in sorted(removed_subjects, key=_sort_key)
    )

    changed = []
    for subject in sorted(common_subjects, key=_sort_key):
        added_values = second_by_subject[subject] - first_by_subject[subject]
        removed_values = first_by_subject[subject] - second_by_subject[subject]
        if added_values or removed_values:
            changed.append(_resource_diff(subject, added=added_values, removed=removed_values))

    return ModelDiff(
        first_file=Path(first_file),
        second_file=Path(second_file),
        first_triple_count=first_triple_count,
        second_triple_count=second_triple_count,
        added_resources=added_resources,
        removed_resources=removed_resources,
        changed_resources=tuple(changed),
    )


def format_term(term: Node, graph: Graph | None = None) -> str:
    if graph is not None:
        try:
            return graph.namespace_manager.normalizeUri(term)
        except Exception:
            pass

    if hasattr(term, "n3"):
        return term.n3()
    return str(term)


def predicate_value_text(item: PredicateValue, graph: Graph | None = None) -> str:
    return f"{format_term(item.predicate, graph)} -> {format_term(item.value, graph)}"


def _subject_map(graph: Graph) -> dict[Node, set[PredicateValue]]:
    subjects: dict[Node, set[PredicateValue]] = {}
    opm_state_nodes = set(graph.subjects(RDF.type, OPM_CURRENT_PROPERTY_STATE))
    opm_state_nodes.update(graph.objects(None, OPM_HAS_PROPERTY_STATE))
    opm_property_nodes = set(graph.subjects(RDF.type, OPM_PROPERTY))
    opm_property_nodes.update(graph.subjects(SCHEMA_VALUE, None))
    opm_property_nodes.update(graph.subjects(OPM_HAS_PROPERTY_STATE, None))
    opm_property_nodes.difference_update(opm_state_nodes)

    for subject, predicate, value in _opm_canonical_triples(graph, opm_property_nodes):
        subjects.setdefault(subject, set()).add(PredicateValue(predicate, value))

    for subject, predicate, value in graph:
        if _ignore_triple(subject, predicate, value, opm_property_nodes, opm_state_nodes):
            continue
        normalized_subject = _comparison_term(subject)
        normalized_predicate = _comparison_predicate(predicate)
        normalized_value = _comparison_term(value)
        subjects.setdefault(normalized_subject, set()).add(
            PredicateValue(normalized_predicate, normalized_value)
        )
    return subjects


def _opm_canonical_triples(
    graph: Graph,
    opm_property_nodes: set[Node],
) -> set[tuple[Node, Node, Node]]:
    triples = set()
    for owner, predicate, property_node in graph:
        if property_node not in opm_property_nodes:
            continue

        values = set(graph.objects(property_node, SCHEMA_VALUE))
        for state_node in graph.objects(property_node, OPM_HAS_PROPERTY_STATE):
            values.update(graph.objects(state_node, SCHEMA_VALUE))

        for value in values:
            triples.add(
                (
                    _comparison_term(owner),
                    _comparison_predicate(predicate),
                    _comparison_term(value),
                )
            )

        units = set(graph.objects(property_node, SMLS_UNIT))
        for state_node in graph.objects(property_node, OPM_HAS_PROPERTY_STATE):
            units.update(graph.objects(state_node, SMLS_UNIT))

        for unit in units:
            triples.add(
                (
                    _comparison_term(owner),
                    _opm_unit_predicate(predicate),
                    _comparison_term(unit),
                )
            )
    return triples


def _ignore_triple(
    subject: Node,
    predicate: Node,
    value: Node,
    opm_property_nodes: set[Node],
    opm_state_nodes: set[Node],
) -> bool:
    if predicate in IGNORED_PREDICATES:
        return True
    if value in opm_property_nodes:
        return True
    if subject in opm_property_nodes or subject in opm_state_nodes:
        return True
    if predicate == RDF.type and value in {OPM_PROPERTY, OPM_CURRENT_PROPERTY_STATE}:
        return True
    if _is_level_specific_property_declaration(subject, predicate, value):
        return True
    return False


def _is_level_specific_property_declaration(subject: Node, predicate: Node, value: Node) -> bool:
    if not isinstance(subject, URIRef) or not str(subject).startswith(PROPS_NAMESPACE):
        return False
    return (
        (predicate == RDF.type and value in {OWL.DatatypeProperty, OWL.ObjectProperty})
        or predicate == RDFS.comment
    )


def _comparison_term(term: Node) -> Node:
    if isinstance(term, URIRef):
        uri = URI_TIMESTAMP_SUFFIX.sub("", str(term))
        for namespace in INSTANCE_NAMESPACES:
            if uri.startswith(namespace):
                return URIRef(f"{CANONICAL_INSTANCE_NAMESPACE}{uri[len(namespace):]}")
        return URIRef(uri)
    return term


def _comparison_predicate(term: Node) -> Node:
    if isinstance(term, URIRef):
        uri = URI_TIMESTAMP_SUFFIX.sub("", str(term))
        if uri.startswith(PROPS_NAMESPACE):
            uri = PROPERTY_SUFFIX.sub("", uri)
        return URIRef(uri)
    return term


def _opm_unit_predicate(term: Node) -> Node:
    predicate = _comparison_predicate(term)
    if isinstance(predicate, URIRef):
        return URIRef(f"{predicate}/unit")
    return SMLS_UNIT


def _resource_diff(
    subject: Node,
    added: set[PredicateValue],
    removed: set[PredicateValue],
) -> ResourceDiff:
    return ResourceDiff(
        subject=subject,
        added=tuple(sorted(added, key=_predicate_value_sort_key)),
        removed=tuple(sorted(removed, key=_predicate_value_sort_key)),
    )


def _predicate_value_sort_key(item: PredicateValue) -> tuple[str, str]:
    return _sort_key(item.predicate), _sort_key(item.value)


def _sort_key(term: Node) -> str:
    if hasattr(term, "n3"):
        return term.n3()
    return str(term)
