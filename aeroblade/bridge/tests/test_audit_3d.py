import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from audit_3d import _zero_fixed_value, audit_3d, parse_ascii_field


def write_case(root, *, empty=False, with_c=True, bad_count=False, zero_span=False,
               dimensions=3, zero_face=False, uz=(0.0, 0.2, 0.4, 0.6)):
    case = root / "case"
    mesh = case / "constant" / "polyMesh"
    time = case / "10"
    mesh.mkdir(parents=True)
    time.mkdir()
    (root / "job.json").write_text(
        json.dumps({"id": "fixture", "solver": "rhoSimpleFoam", "status": "completed"})
    )
    (root / "run.log").write_text(
        f"--- checkMesh ---\nMesh OK.\nMesh has {dimensions} solution dimensions\ncells: 4\nCoupled point location match\n"
        "--- rhoSimpleFoam ---\n"
        "Time = 1\n"
        "Ux: Solving for Ux, Initial residual = 1e-6, Final residual = 1e-8\n"
        "Uy: Solving for Uy, Initial residual = 1e-6, Final residual = 1e-8\n"
        "Uz: Solving for Uz, Initial residual = 1e-6, Final residual = 1e-8\n"
        "p: Solving for p, Initial residual = 1e-6, Final residual = 1e-8\n"
        "h: Solving for h, Initial residual = 1e-6, Final residual = 1e-8\n"
        "k: Solving for k, Initial residual = 1e-6, Final residual = 1e-8\n"
        "omega: Solving for omega, Initial residual = 1e-6, Final residual = 1e-8\n"
        "sum(inlet) of phi = -1\n"
        "sum(outlet) of phi = 1\n"
        "SIMPLE solution converged in 1 iterations\nEnd\n"
    )
    boundary_type = "empty" if empty else "wall"
    (mesh / "boundary").write_text(
        "FoamFile {version 2.0; format ascii;}\n"
        "6\n(\n"
        f"spanLow {{ type {boundary_type}; nFaces {0 if zero_face else 1}; startFace 0; }}\n"
        f"spanHigh {{ type {boundary_type}; nFaces 1; startFace 1; }}\n"
        "inlet { type patch; nFaces 1; startFace 2; }\n"
        "outlet { type patch; nFaces 1; startFace 3; }\n"
        "cyclicLow { type cyclic; nFaces 1; startFace 4; neighbourPatch cyclicHigh; }\n"
        "cyclicHigh { type cyclic; nFaces 1; startFace 4; neighbourPatch cyclicLow; }\n)\n"
    )

    def field(name, body):
        (time / name).write_text("FoamFile {version 2.0; format ascii;}\n" + body)

    field("U", "dimensions [0 1 -1 0 0 0 0];\ninternalField nonuniform List<vector> 4\n(\n" +
          "\n".join(f"(1 0 {value})" for value in uz) + "\n);\nboundaryField { spanLow { type noSlip; } spanHigh { type noSlip; } }\n")
    if with_c:
        field("C", "dimensions [0 1 0 0 0 0 0];\ninternalField nonuniform List<vector> 4\n"
              "((0 0 0) (0 0 0) (0 0 0) (0 0 0));\n" if zero_span else
              "dimensions [0 1 0 0 0 0 0];\ninternalField nonuniform List<vector> 4\n"
              "((0 0 -0.004) (0 0 -0.001) (0 0 0.001) (0 0 0.004));\n")
    if bad_count:
        field("C", "dimensions [0 1 0 0 0 0 0];\ninternalField nonuniform List<vector> 3\n"
              "((0 0 -0.004) (0 0 0) (0 0 0.004));\n")
    for name in ["p", "h", "k", "omega"]:
        field(name, "dimensions [0 0 0 0 0 0 0]; internalField uniform 1;\n")
    field("T", "dimensions [0 0 0 1 0 0 0]; internalField uniform 300;\n"
          "boundaryField { spanLow { type zeroGradient; } spanHigh { type zeroGradient; } }\n")
    (case / "VTK").mkdir()
    (case / "VTK" / "fixture.vtu").write_text("fixture")
    (root / "results.zip").write_bytes(b"fixture")
    return root


class Audit3DTests(unittest.TestCase):
    def test_rejects_extra_tokens_and_wrong_vector_grouping(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'U'
            for body in ['(1 2 3 junk)', '(1 2 3 NaN)', '(1 2) (3)', '(1 nan 3)']:
                path.write_text('FoamFile {format ascii;} internalField nonuniform List<vector> 1 (' + body + ');')
                with self.assertRaises(ValueError):
                    parse_ascii_field(path, components=3, expected_count=1)

    def test_missing_reported_dimensions_cannot_verify_3d(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = write_case(pathlib.Path(tmp))
            log = root / 'run.log'
            log.write_text(log.read_text().replace('Mesh has 3 solution dimensions\n', ''))
            result = audit_3d(root)
            self.assertIsNone(result['solution_dimensions'])
            self.assertFalse(result['workflow_3d_verified'])
            self.assertFalse(result['three_dimensional_flow_detected'])

    def test_rejects_nonuniform_field_with_bad_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = write_case(pathlib.Path(tmp), bad_count=True)
            with self.assertRaisesRegex(ValueError, "count"):
                parse_ascii_field(root / "case" / "10" / "C", components=3, expected_count=4)

    def test_rejects_two_dimensional_empty_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = audit_3d(write_case(pathlib.Path(tmp), empty=True))
            self.assertEqual(result["solution_dimensions"], 3)
            self.assertFalse(result["workflow_3d_verified"])
            self.assertFalse(result["three_dimensional_flow_detected"])
            self.assertIn("empty/wedge", " ".join(result["limitations"]))

    def test_reports_boundary_checks_and_positive_span_flow_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = audit_3d(write_case(pathlib.Path(tmp)))
            self.assertEqual(result["solution_dimensions"], 3)
            self.assertEqual(result["endwall_types"], {"spanLow": "wall", "spanHigh": "wall"})
            self.assertEqual(result["endwall_count"], 2)
            self.assertTrue(result["noSlip"])
            self.assertTrue(result["temperature_zeroGradient"])
            self.assertTrue(result["workflow_3d_verified"])
            self.assertTrue(result["three_dimensional_flow_detected"])
            self.assertAlmostEqual(result["maxabsUz"], 0.6)
            self.assertEqual(sum(result["bins"]["counts"]), 4)
            self.assertTrue((pathlib.Path(tmp) / "audit-3d.json").exists())

    def test_missing_centres_keeps_flow_diagnostic_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = audit_3d(write_case(pathlib.Path(tmp), with_c=False))
            self.assertIsNone(result["z_span"])
            self.assertIsNone(result["three_dimensional_flow_detected"])
            self.assertIn("C", " ".join(result["limitations"]))

    def test_zero_face_wall_does_not_verify_endwalls(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = audit_3d(write_case(pathlib.Path(tmp), zero_face=True))
            self.assertEqual(result["endwall_face_counts"]["spanLow"], 0)
            self.assertFalse(result["workflow_3d_verified"])

    def test_checkmesh_dimensions_gate_detection_without_empty_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = audit_3d(write_case(pathlib.Path(tmp), dimensions=2))
            self.assertEqual(result["solution_dimensions"], 2)
            self.assertFalse(result["three_dimensional_flow_detected"])

    def test_zero_z_span_is_reported_without_division_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = audit_3d(write_case(pathlib.Path(tmp), zero_span=True))
            self.assertEqual(result["z_span"], 0.0)
            self.assertFalse(result["three_dimensional_flow_detected"])
            self.assertIn("zero z span", " ".join(result["limitations"]))

    def test_fixed_value_requires_exact_finite_zero_vector(self):
        self.assertTrue(_zero_fixed_value("type fixedValue; value uniform (0 0 0);"))
        self.assertFalse(_zero_fixed_value("type fixedValue; value uniform (0 0);"))
        self.assertFalse(_zero_fixed_value("type fixedValue; value uniform (0 nan 0);"))
        self.assertFalse(_zero_fixed_value("type fixedValue; value uniform junk;"))


if __name__ == "__main__":
    unittest.main()
