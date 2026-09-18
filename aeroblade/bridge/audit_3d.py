"""Bounded sidecar audit for actual AeroBlade 3D OpenFOAM results."""
import json
import math
import pathlib
import re

from validate_result import audit as generic_audit

MAX_FIELD_BYTES = 32 * 1024 * 1024
MAX_VALUES = 6_000_000
BIN_COUNT = 5
UZ_EPSILON = 1e-8

_NUMBER = r"[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?"


def _read_ascii(path):
    path = pathlib.Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("field is unavailable")
    if path.stat().st_size > MAX_FIELD_BYTES:
        raise ValueError("field exceeds bounded audit size")
    text = path.read_text(encoding="utf-8")
    if not re.search(r"\bformat\s+ascii\s*;", text):
        raise ValueError("audit requires ASCII OpenFOAM fields")
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)


def parse_ascii_field(path, *, components, expected_count):
    """Read an ASCII internalField, enforcing its declared count and finiteness."""
    if not isinstance(expected_count, int) or isinstance(expected_count, bool) or expected_count <= 0:
        raise ValueError("field count is invalid")
    if expected_count > MAX_VALUES // components:
        raise ValueError("field count exceeds bounded audit size")
    text = _read_ascii(path)
    pattern = (r"internalField\s+nonuniform\s+List<(scalar|vector)>\s+(\d+)\s*"
               r"\((.*?)\)\s*;" )
    match = re.search(pattern, text, re.S)
    if match:
        kind, declared, body = match.groups()
        if int(declared) != expected_count or (kind == "vector") != (components == 3):
            raise ValueError("field count or component mismatch")
        if components == 3:
            vectors = re.findall(r"\(([^()]*)\)", body)
            if len(vectors) != expected_count or re.sub(r"\([^()]*\)", "", body).strip():
                raise ValueError("malformed vector list")
            if any(len(vector.split()) != 3 for vector in vectors):
                raise ValueError("vector must have three components")
            values = [float(value) for vector in vectors for value in vector.split()]
        else:
            values = [float(value) for value in body.split()]
    else:
        match = re.search(r"internalField\s+uniform\s+([^;]+);", text)
        if not match:
            raise ValueError("internalField is not readable")
        body = match.group(1).strip()
        if components == 3:
            if not re.fullmatch(r"\([^()]*\)", body):
                raise ValueError("malformed uniform vector")
            body = body[1:-1]
        values = [float(value) for value in body.split()]
        if len(values) != components:
            raise ValueError("uniform field component mismatch")
        values *= expected_count
    if len(values) != expected_count * components:
        raise ValueError("field value count mismatch")
    if len(values) > MAX_VALUES or not all(math.isfinite(value) for value in values):
        raise ValueError("field contains too many or non-finite values")
    return values, text


def _blocks(text):
    return {name: body for name, body in re.findall(r"([\w.-]+)\s*\{([^{}]*)\}", text)}


def _patch_type(body):
    match = re.search(r"\btype\s+([\w.-]+)\s*;", body)
    return match.group(1) if match else None


def _boundary_checks(boundary):
    blocks = _blocks(_read_ascii(boundary))
    types = {name: _patch_type(body) for name, body in blocks.items()}
    has_2d_patch = any(value in {"empty", "wedge"} for value in types.values())
    endwalls = {name: types.get(name) for name in ("spanLow", "spanHigh")}
    endwall_face_counts = {}
    for name in endwalls:
        match = re.search(r"\bnFaces\s+(\d+)", blocks.get(name, ""))
        endwall_face_counts[name] = int(match.group(1)) if match else 0
    endwall_count = sum(value == "wall" for value in endwalls.values())
    return types, has_2d_patch, endwalls, endwall_face_counts, endwall_count, blocks


def _field_boundary_types(text):
    return {name: _patch_type(body) for name, body in _blocks(text).items()}


def _zero_fixed_value(body):
    match = re.search(r"\btype\s+fixedValue\s*;[^{}]*?\bvalue\s+uniform\s*\(([^()]*)\)\s*;", body, re.S)
    if not match:
        return False
    tokens = match.group(1).split()
    if len(tokens) != 3:
        return False
    try:
        values = [float(token) for token in tokens]
    except ValueError:
        return False
    return all(math.isfinite(value) and value == 0.0 for value in values)


def _latest_time(case):
    times = [path for path in case.iterdir()
             if path.is_dir() and not path.is_symlink() and re.fullmatch(_NUMBER, path.name)
             and math.isfinite(float(path.name)) and float(path.name) > 0]
    return max(times, key=lambda path: float(path.name)) if times else None


def _metrics(u, centres):
    z = centres[2::3]
    speeds = [math.sqrt(sum(u[i + j] ** 2 for j in range(3))) for i in range(0, len(u), 3)]
    abs_uz = [abs(u[i + 2]) for i in range(0, len(u), 3)]
    low, high = min(z), max(z)
    span = high - low
    if span <= 0.0:
        return {"z_min": low, "z_max": high, "z_span": span, "valid": False,
                "reason": "zero z span; span bins and 3D flow detection are unavailable."}
    counts = [0] * BIN_COUNT
    speed_sums = [0.0] * BIN_COUNT
    uz_sums = [0.0] * BIN_COUNT
    for coordinate, speed, uz in zip(z, speeds, abs_uz):
        index = BIN_COUNT - 1 if coordinate == high else min(BIN_COUNT - 1, int((coordinate - low) / span * BIN_COUNT))
        counts[index] += 1
        speed_sums[index] += speed
        uz_sums[index] += uz
    mean_speed = [speed_sums[i] / counts[i] if counts[i] else None for i in range(BIN_COUNT)]
    mean_abs_uz = [uz_sums[i] / counts[i] if counts[i] else None for i in range(BIN_COUNT)]
    variation = max(value for value in mean_speed if value is not None) - min(value for value in mean_speed if value is not None)
    return dict(z_span=span, bins={"count": BIN_COUNT, "counts": counts,
                                   "mean_speed": mean_speed, "mean_abs_Uz": mean_abs_uz},
                z_min=low, z_max=high, span_variation=variation,
                maxabsUz=max(abs_uz), typical_speed=sum(speeds) / len(speeds), valid=True)


def audit_3d(folder):
    folder = pathlib.Path(folder)
    generic = generic_audit(folder)
    case = folder / "case"
    boundary = case / "constant" / "polyMesh" / "boundary"
    types, has_2d_patch, endwalls, endwall_face_counts, endwall_count, blocks = _boundary_checks(boundary)
    latest = _latest_time(case)
    if latest is None:
        raise ValueError("no latest written time")
    u_match = re.search(r"nonuniform\s+List<vector>\s+(\d+)", _read_ascii(latest / "U"))
    if not u_match:
        raise ValueError("U must be a nonuniform vector field for 3D audit")
    actual_cells = generic.get("mesh", {}).get("cells")
    if (not isinstance(actual_cells, (int, float)) or isinstance(actual_cells, bool) or
            not math.isfinite(actual_cells) or actual_cells <= 0 or actual_cells != int(actual_cells)):
        raise ValueError("generic checkMesh did not report a valid cell count")
    actual_cells = int(actual_cells)
    if actual_cells > MAX_VALUES // 3:
        raise ValueError("mesh cell count exceeds bounded audit size")
    cell_count = int(u_match.group(1))
    if cell_count != actual_cells:
        raise ValueError("U count does not match generic checkMesh cells")
    u, u_text = parse_ascii_field(latest / "U", components=3, expected_count=cell_count)
    c_path = latest / "C"
    metrics = None
    limitations = list(generic.get("limitations", []))
    if has_2d_patch:
        limitations.append("empty/wedge boundary detected; this case is treated as 2D and cannot verify a 3D span flow.")
    if c_path.exists():
        centres, _ = parse_ascii_field(c_path, components=3, expected_count=cell_count)
        metrics = _metrics(u, centres)
    else:
        limitations.append("C is missing; spanwise flow evidence is unknown because no actual cell-centre z sampling is available.")

    u_field_blocks = _blocks(u_text)
    u_types = _field_boundary_types(u_text)
    t_path = latest / "T"
    t_types = _field_boundary_types(_read_ascii(t_path)) if t_path.exists() else {}
    no_slip = all(u_types.get(name) == "noSlip" or _zero_fixed_value(u_field_blocks.get(name, ""))
                  for name in ("spanLow", "spanHigh"))
    temperature_zero_gradient = all(t_types.get(name) == "zeroGradient" for name in ("spanLow", "spanHigh"))
    mesh_log = (folder / "run.log").read_text(errors="replace").split("--- checkMesh ---")[-1].split("\n--- ")[0]
    reported_dimensions = re.search(r"Mesh has (\d+) solution", mesh_log)
    dimensions = int(reported_dimensions.group(1)) if reported_dimensions else None
    boundary_pass = (dimensions == 3 and not has_2d_patch and endwall_count == 2 and
                     all(count > 0 for count in endwall_face_counts.values()) and
                     all(endwalls.values()) and no_slip and temperature_zero_gradient)
    workflow_verified = bool(generic.get("workflow_verified")) and boundary_pass
    detected = None
    if metrics is not None:
        if not metrics["valid"]:
            limitations.append(metrics["reason"])
            detected = False
        else:
            threshold = max(UZ_EPSILON, 1e-5 * metrics["typical_speed"])
            detected = bool(boundary_pass and metrics["maxabsUz"] > threshold and metrics["span_variation"] > threshold)
            limitations.append("Detection requires maxabsUz and span-binned mean-speed variation above max(1e-8, 1e-5 * typical speed); adaptive XY sampling can bias unweighted means, so this is not engineering validation.")
    result = {
        "solution_dimensions": dimensions, "latest_written_time": latest.name,
        "finite_values": {"U": True, "C": True if metrics is not None else None},
        "endwall_types": endwalls, "endwall_face_counts": endwall_face_counts, "endwall_count": endwall_count,
        "noSlip": no_slip, "temperature_zeroGradient": temperature_zero_gradient,
        "z_min": metrics.get("z_min") if metrics else None, "z_max": metrics.get("z_max") if metrics else None,
        "z_span": metrics["z_span"] if metrics else None,
        "bin_edges": ([metrics["z_min"] + i * metrics["z_span"] / BIN_COUNT for i in range(BIN_COUNT + 1)]
                      if metrics and metrics["valid"] else None),
        "bins": metrics.get("bins") if metrics and metrics["valid"] else {"count": BIN_COUNT, "counts": None, "mean_speed": None, "mean_abs_Uz": None},
        "maxabsUz": metrics.get("maxabsUz") if metrics else None,
        "workflow_3d_verified": workflow_verified,
        "three_dimensional_flow_detected": detected,
        "limitations": limitations,
    }
    (folder / "audit-3d.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=pathlib.Path)
    args = parser.parse_args()
    report = audit_3d(args.folder)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["workflow_3d_verified"] else 2)
