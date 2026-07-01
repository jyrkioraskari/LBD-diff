from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from lbd_diff.diff_engine import diff_turtle_files


class DiffEngineTest(unittest.TestCase):
    def test_detects_added_removed_and_changed_resources(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            first = tmp_path / "first.ttl"
            second = tmp_path / "second.ttl"

            first.write_text(
                """
@prefix ex: <https://example.org/> .

ex:wall-1 ex:name "Wall A" ;
    ex:height "3.0" .
ex:door-1 ex:name "Door A" .
""".strip(),
                encoding="utf-8",
            )
            second.write_text(
                """
@prefix ex: <https://example.org/> .

ex:wall-1 ex:name "Wall A" ;
    ex:height "3.2" .
ex:window-1 ex:name "Window A" .
""".strip(),
                encoding="utf-8",
            )

            diff = diff_turtle_files(first, second)

        self.assertEqual(1, len(diff.added_resources))
        self.assertEqual(1, len(diff.removed_resources))
        self.assertEqual(1, len(diff.changed_resources))

        changed = diff.changed_resources[0]
        self.assertEqual(1, len(changed.added))
        self.assertEqual(1, len(changed.removed))
        self.assertTrue(diff.has_changes)

    def test_identical_graphs_have_no_changes(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            first = tmp_path / "first.ttl"
            second = tmp_path / "second.ttl"
            content = '@prefix ex: <https://example.org/> . ex:a ex:name "A" .'
            first.write_text(content, encoding="utf-8")
            second.write_text(content, encoding="utf-8")

            diff = diff_turtle_files(first, second)

        self.assertFalse(diff.has_changes)

    def test_ignores_prov_generated_at_time_triples(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            first = tmp_path / "first.ttl"
            second = tmp_path / "second.ttl"

            first.write_text(
                """
@prefix ex: <https://example.org/> .
@prefix prov: <http://www.w3.org/ns/prov#> .

ex:model ex:name "Model A" ;
    prov:generatedAtTime "2026-07-01T10:00:00Z" .
ex:metadata prov:generatedAtTime "2026-07-01T10:01:00Z" .
""".strip(),
                encoding="utf-8",
            )
            second.write_text(
                """
@prefix ex: <https://example.org/> .
@prefix prov: <http://www.w3.org/ns/prov#> .

ex:model ex:name "Model A" ;
    prov:generatedAtTime "2026-07-01T11:00:00Z" .
ex:metadata prov:generatedAtTime "2026-07-01T11:01:00Z" .
""".strip(),
                encoding="utf-8",
            )

            diff = diff_turtle_files(first, second)

        self.assertFalse(diff.has_changes)
        self.assertEqual(1, diff.first_triple_count)
        self.assertEqual(1, diff.second_triple_count)

    def test_ignores_uri_timestamp_suffixes_in_comparison(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            first = tmp_path / "first.ttl"
            second = tmp_path / "second.ttl"

            first.write_text(
                """
@prefix ex: <https://example.org/> .

ex:wallp1234 ex:name "Wall A" ;
    ex:connectedTo ex:spacep5678 .
""".strip(),
                encoding="utf-8",
            )
            second.write_text(
                """
@prefix ex: <https://example.org/> .

ex:wallp9876 ex:name "Wall A" ;
    ex:connectedTo ex:spacep4321 .
""".strip(),
                encoding="utf-8",
            )

            diff = diff_turtle_files(first, second)

        self.assertFalse(diff.has_changes)
        self.assertEqual(2, diff.first_triple_count)
        self.assertEqual(2, diff.second_triple_count)

    def test_standardizes_known_instance_base_uris(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            first = tmp_path / "first.ttl"
            second = tmp_path / "second.ttl"

            first.write_text(
                """
@prefix inst: <https://www.ugent.be/myAwesomeFirstBIMProject#> .
@prefix bot: <https://w3id.org/bot#> .
@prefix props: <http://lbd.arch.rwth-aachen.de/props#> .

inst:wall_1 a bot:Element ;
    props:globalIdIfcRoot "abc" ;
    bot:hasSubElement inst:window_1 .
inst:window_1 a bot:Element .
""".strip(),
                encoding="utf-8",
            )
            second.write_text(
                """
@prefix inst: <https://lbd.example.com/> .
@prefix bot: <https://w3id.org/bot#> .
@prefix props: <http://lbd.arch.rwth-aachen.de/props#> .

inst:wall_1 a bot:Element ;
    props:globalIdIfcRoot_attribute_simple "abc" ;
    bot:hasSubElement inst:window_1 .
inst:window_1 a bot:Element .
""".strip(),
                encoding="utf-8",
            )

            diff = diff_turtle_files(first, second)

        self.assertFalse(diff.has_changes)

    def test_compares_opm_level_1_and_2_as_direct_properties(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            first = tmp_path / "first.ttl"
            second = tmp_path / "second.ttl"

            first.write_text(
                """
@prefix ex: <https://example.org/> .
@prefix props: <http://lbd.arch.rwth-aachen.de/props#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

ex:wall props:FireRating_property_simple "EI30" .
props:FireRating_property_simple a owl:DatatypeProperty ;
    rdfs:comment "IFC property set Pset_WallCommon property FireRating" .
""".strip(),
                encoding="utf-8",
            )
            second.write_text(
                """
@prefix ex: <https://example.org/> .
@prefix opm: <https://w3id.org/opm#> .
@prefix props: <http://lbd.arch.rwth-aachen.de/props#> .
@prefix schema: <http://schema.org/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

ex:wall props:FireRating ex:FireRating_wall .
ex:FireRating_wall a opm:Property ;
    rdfs:label "Pset_WallCommon:FireRating" ;
    schema:value "EI30" .
props:FireRating a owl:ObjectProperty ;
    rdfs:comment "IFC property set Pset_WallCommon property FireRating" .
""".strip(),
                encoding="utf-8",
            )

            diff = diff_turtle_files(first, second)

        self.assertFalse(diff.has_changes)

    def test_compares_opm_level_2_and_3_as_direct_properties(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            first = tmp_path / "first.ttl"
            second = tmp_path / "second.ttl"

            first.write_text(
                """
@prefix ex: <https://example.org/> .
@prefix opm: <https://w3id.org/opm#> .
@prefix props: <http://lbd.arch.rwth-aachen.de/props#> .
@prefix schema: <http://schema.org/> .

ex:wall props:FireRating ex:FireRating_wall .
ex:FireRating_wall a opm:Property ;
    schema:value "EI30" .
""".strip(),
                encoding="utf-8",
            )
            second.write_text(
                """
@prefix ex: <https://example.org/> .
@prefix opm: <https://w3id.org/opm#> .
@prefix props: <http://lbd.arch.rwth-aachen.de/props#> .
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix schema: <http://schema.org/> .

ex:wall props:FireRating ex:FireRating_wall .
ex:FireRating_wall a opm:Property ;
    opm:hasPropertyState ex:state_FireRating_wall_p1234 .
ex:state_FireRating_wall_p1234 a opm:CurrentPropertyState ;
    prov:generatedAtTime "2026-07-01T10:00:00Z" ;
    schema:value "EI30" .
""".strip(),
                encoding="utf-8",
            )

            diff = diff_turtle_files(first, second)

        self.assertFalse(diff.has_changes)

    def test_detects_opm_value_changes_after_level_normalization(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            first = tmp_path / "first.ttl"
            second = tmp_path / "second.ttl"

            first.write_text(
                """
@prefix ex: <https://example.org/> .
@prefix opm: <https://w3id.org/opm#> .
@prefix props: <http://lbd.arch.rwth-aachen.de/props#> .
@prefix schema: <http://schema.org/> .

ex:wall props:FireRating ex:FireRating_wall .
ex:FireRating_wall a opm:Property ;
    schema:value "EI30" .
""".strip(),
                encoding="utf-8",
            )
            second.write_text(
                """
@prefix ex: <https://example.org/> .
@prefix opm: <https://w3id.org/opm#> .
@prefix props: <http://lbd.arch.rwth-aachen.de/props#> .
@prefix schema: <http://schema.org/> .

ex:wall props:FireRating ex:FireRating_wall .
ex:FireRating_wall a opm:Property ;
    schema:value "EI60" .
""".strip(),
                encoding="utf-8",
            )

            diff = diff_turtle_files(first, second)

        self.assertTrue(diff.has_changes)
        self.assertEqual(1, len(diff.changed_resources))

    def test_compares_opm_units_after_level_normalization(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            first = tmp_path / "first.ttl"
            second = tmp_path / "second.ttl"

            first.write_text(
                """
@prefix ex: <https://example.org/> .
@prefix opm: <https://w3id.org/opm#> .
@prefix props: <http://lbd.arch.rwth-aachen.de/props#> .
@prefix schema: <http://schema.org/> .
@prefix smls: <https://w3id.org/smls/> .
@prefix unit: <http://qudt.org/vocab/unit/> .

ex:wall props:Height ex:Height_wall .
ex:Height_wall a opm:Property ;
    schema:value "3000" ;
    smls:unit unit:MilliM .
""".strip(),
                encoding="utf-8",
            )
            second.write_text(
                """
@prefix ex: <https://example.org/> .
@prefix opm: <https://w3id.org/opm#> .
@prefix props: <http://lbd.arch.rwth-aachen.de/props#> .
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix schema: <http://schema.org/> .
@prefix smls: <https://w3id.org/smls/> .
@prefix unit: <http://qudt.org/vocab/unit/> .

ex:wall props:Height ex:Height_wall .
ex:Height_wall a opm:Property ;
    opm:hasPropertyState ex:state_Height_wall_p1234 .
ex:state_Height_wall_p1234 a opm:CurrentPropertyState ;
    prov:generatedAtTime "2026-07-01T10:00:00Z" ;
    schema:value "3000" ;
    smls:unit unit:MilliM .
""".strip(),
                encoding="utf-8",
            )

            diff = diff_turtle_files(first, second)

        self.assertFalse(diff.has_changes)

    def test_detects_opm_unit_changes_after_level_normalization(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            first = tmp_path / "first.ttl"
            second = tmp_path / "second.ttl"

            first.write_text(
                """
@prefix ex: <https://example.org/> .
@prefix opm: <https://w3id.org/opm#> .
@prefix props: <http://lbd.arch.rwth-aachen.de/props#> .
@prefix schema: <http://schema.org/> .
@prefix smls: <https://w3id.org/smls/> .
@prefix unit: <http://qudt.org/vocab/unit/> .

ex:wall props:Height ex:Height_wall .
ex:Height_wall a opm:Property ;
    schema:value "3000" ;
    smls:unit unit:MilliM .
""".strip(),
                encoding="utf-8",
            )
            second.write_text(
                """
@prefix ex: <https://example.org/> .
@prefix opm: <https://w3id.org/opm#> .
@prefix props: <http://lbd.arch.rwth-aachen.de/props#> .
@prefix schema: <http://schema.org/> .
@prefix smls: <https://w3id.org/smls/> .
@prefix unit: <http://qudt.org/vocab/unit/> .

ex:wall props:Height ex:Height_wall .
ex:Height_wall a opm:Property ;
    schema:value "3000" ;
    smls:unit unit:M .
""".strip(),
                encoding="utf-8",
            )

            diff = diff_turtle_files(first, second)

        self.assertTrue(diff.has_changes)
        self.assertEqual(1, len(diff.changed_resources))


if __name__ == "__main__":
    unittest.main()
