#!/usr/bin/env python3
"""Inspect or explicitly exercise the real PyTC/em_erl CPU evaluator.

This adapter never reproduces or promotes an NISB scientific result. Inspection
and receipt verification do not import the evaluator or its numerical stack.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.machinery
import importlib.metadata
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
EVALUATOR_ID = "connectomics/metrics/nerl.py"
SCHEMA = "probe.nerl-regression.v1"


def digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def file_record(path, source_id):
    return {"id": source_id, "path": str(path.resolve()), "sha256": digest_bytes(path.read_bytes())}


def git_revision(path):
    try:
        return subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL, text=True, timeout=5,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def find_backend(backend_repo):
    """Locate source without importing em_erl or executing its __init__."""
    if backend_repo is not None:
        base = backend_repo.resolve()
        for parent in (base, base / "src"):
            if (parent / "em_erl" / "__init__.py").is_file():
                return parent / "em_erl"
        raise ValueError("--backend-repo must contain em_erl/__init__.py (or src/em_erl)")
    spec = importlib.machinery.PathFinder.find_spec("em_erl", sys.path)
    if spec and spec.origin and spec.submodule_search_locations:
        return Path(spec.origin).resolve().parent
    return None


def fingerprint(code_repo, backend):
    evaluator = code_repo / EVALUATOR_ID
    if not evaluator.is_file():
        raise ValueError(f"Required evaluator is absent: {evaluator}")
    records = [
        file_record(HERE / "nerl_adapter.py", "adapter/nerl_adapter.py"),
        file_record(HERE / "fixtures.json", "inputs/fixtures.json"),
        file_record(evaluator, EVALUATOR_ID),
    ]
    if backend:
        files = sorted(p for p in backend.rglob("*") if p.is_file()
                       and "__pycache__" not in p.parts
                       and (p.suffix in {".py", ".so", ".pyd", ".dll", ".dylib"}))
        records.extend(file_record(p, "em_erl/" + p.relative_to(backend).as_posix()) for p in files)
    identities = [{"id": entry["id"], "sha256": entry["sha256"]} for entry in records]
    return {"files": records, "sha256": digest_bytes(canonical(identities))}


def load_fixture():
    fixture = json.loads((HERE / "fixtures.json").read_text())
    checks = fixture.get("checks") if isinstance(fixture, dict) else None
    if not isinstance(checks, list) or not checks:
        raise ValueError("Fixture must contain a nonempty checks list")
    for case in checks:
        if not isinstance(case, dict) or not isinstance(case.get("expected"), dict) or not case["expected"]:
            raise ValueError("Every fixture check must contain nonempty expected assertions")
    return fixture


def inspect(code_repo, backend_repo):
    backend = find_backend(backend_repo)
    fixture = load_fixture()
    missing = [name for name in ("numpy", "networkx")
               if importlib.machinery.PathFinder.find_spec(name, sys.path) is None]
    if backend is None:
        missing.append("em_erl")
    return {
        "schema_version": SCHEMA,
        "kind": "evaluator_regression",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "execution": {"status": "not_run", "mode": "inspect"},
        "validity": {"status": "unknown", "reason": "Evaluator has not been executed."},
        "scientific_verdict": "not_evaluated",
        "baseline_reproduced": False,
        "readiness": {"status": "unavailable" if missing else "not_tested", "missing": missing},
        "code_repo": {"path": str(code_repo), "git_revision": git_revision(code_repo)},
        "backend": {"package_path": str(backend) if backend else None,
                    "git_revision": git_revision(backend) if backend else None},
        "parameters": fixture["parameters"],
        "graph_options": fixture["graph_options"],
        "input_sha256": digest_bytes(canonical(fixture)),
        "planned_checks": [case["id"] for case in fixture["checks"]],
        "python": {"executable": sys.executable, "version": sys.version},
        "sources_before": fingerprint(code_repo, backend),
        "checks": [],
        "limitations": ["Synthetic regression checks only; no NISB volumes or baseline cache.",
                        "Fingerprints establish byte identity, not scientific validity or authenticity."],
    }, backend


def load_evaluator(path):
    spec = importlib.util.spec_from_file_location("_probe_pytc_nerl", path)
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load PyTC NERL module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclass resolves the defining module
    spec.loader.exec_module(module)
    return module


def observed_matches(observed, expected):
    """Recomputable assertion, shared by execution and receipt consistency checks."""
    if "exception" in expected:
        message = observed.get("message")
        return (observed.get("exception") == expected["exception"]
                and isinstance(message, str)
                and expected.get("message_contains", "") in message)
    try:
        return all(math.isfinite(float(observed[key]))
                   and math.isclose(float(observed[key]), float(value), rel_tol=0, abs_tol=1e-10)
                   for key, value in expected.items())
    except (KeyError, TypeError, ValueError):
        return False


def run_checks(receipt, code_repo, backend):
    receipt["execution"] = {"status": "running", "mode": "run", "device": "cpu"}
    output = io.StringIO()
    try:
        if receipt["readiness"]["missing"]:
            raise ModuleNotFoundError("Unavailable dependencies: " + ", ".join(receipt["readiness"]["missing"]))
        sys.path.insert(0, str(backend.parent))
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            import networkx as nx
            import numpy as np
            import em_erl

            if Path(em_erl.__file__).resolve().parent != backend.resolve():
                raise RuntimeError("Imported backend does not match the inspected em_erl source")
            evaluator = load_evaluator(code_repo / EVALUATOR_ID)
            evaluator.import_em_erl()  # Check the actual three-object backend API.
            fixture = load_fixture()
            receipt["parameters"] = fixture["parameters"]
            receipt["graph_options"] = fixture["graph_options"]
            receipt["input_sha256"] = digest_bytes(canonical(fixture))
            receipt["dependency_versions"] = {}
            for name in ("numpy", "networkx", "imageio"):
                try:
                    receipt["dependency_versions"][name] = importlib.metadata.version(name)
                except importlib.metadata.PackageNotFoundError:
                    receipt["dependency_versions"][name] = None
            skeleton = nx.Graph()
            for part in fixture["skeletons"]:
                for index, position in enumerate(part["nodes_zyx"]):
                    skeleton.add_node((part["id"], index), id=part["id"], index_position=position)
                for left, right in part["edges"]:
                    skeleton.add_edge((part["id"], left), (part["id"], right))
            options = evaluator.NerlGraphOptions(**fixture["graph_options"])
            graph = evaluator.networkx_skeleton_to_erl_graph(
                skeleton, options, resolution=fixture["parameters"]["resolution"]
            )
            for case in fixture["checks"]:
                segmentation = np.zeros(fixture["shape_zyx"], dtype=np.uint32)
                for part, labels in zip(fixture["skeletons"], case["node_segment_ids"]):
                    for position, label in zip(part["nodes_zyx"], labels):
                        segmentation[tuple(position)] = label
                if case.get("invalid_transform") == "take_first_z_slice":
                    segmentation = segmentation[0]
                check = {"id": case["id"], "expected": case["expected"],
                         "rationale": case["rationale"], "pass": False}
                try:
                    result = evaluator.compute_nerl_score_details(
                        segmentation, graph, graph_options=options, **fixture["parameters"]
                    )
                    check["observed"] = {}
                    for key in ("nerl", "pred_erl", "gt_erl", "num_skeletons"):
                        value = getattr(result, key)
                        check["observed"][key] = value if math.isfinite(float(value)) else str(value)
                except Exception as exc:
                    check["observed"] = {"exception": type(exc).__name__, "message": str(exc)}
                check["pass"] = observed_matches(check["observed"], case["expected"])
                receipt["checks"].append(check)
        receipt["execution"]["status"] = "completed"
        receipt["validity"] = {"status": "pass" if all(c["pass"] for c in receipt["checks"]) else "fail",
                               "reason": "Synthetic checks against the real evaluator; not a scientific result."}
    except Exception as exc:
        receipt["execution"]["status"] = "error"
        receipt["error"] = {"type": type(exc).__name__, "message": str(exc)}
        receipt["validity"] = {"status": "unknown", "reason": "Checks could not complete."}
    finally:
        receipt["diagnostics"] = output.getvalue()
        try:
            receipt["sources_after"] = fingerprint(code_repo, backend)
            stable = receipt["sources_before"] == receipt["sources_after"]
        except (OSError, ValueError) as exc:
            stable = False
            receipt["source_check_error"] = str(exc)
        receipt["sources_stable"] = stable
        if not stable:
            receipt["validity"] = {"status": "invalid", "reason": "Source fingerprints changed during execution."}
    return receipt


def verify_receipt(path, code_repo, backend_repo):
    receipt = json.loads(path.read_text())
    if not isinstance(receipt, dict):
        raise ValueError("Receipt must be a JSON object")
    claimed = receipt.pop("receipt_sha256", None)
    intact = claimed == digest_bytes(canonical(receipt))
    backend = find_backend(backend_repo)
    current = fingerprint(code_repo, backend)
    def manifest_matches(original):
        if not isinstance(original, dict) or not isinstance(original.get("files"), list):
            return False
        entries = original["files"]
        if not all(isinstance(entry, dict) for entry in entries):
            return False
        identities = [{"id": entry.get("id"), "sha256": entry.get("sha256")} for entry in entries]
        current_ids = [{"id": entry["id"], "sha256": entry["sha256"]} for entry in current["files"]]
        return identities == current_ids and original.get("sha256") == current["sha256"]

    matches = all(manifest_matches(receipt.get(key)) for key in ("sources_before", "sources_after"))
    fixture = load_fixture()
    fixture_hash = digest_bytes(canonical(fixture))
    inputs_match = receipt.get("input_sha256") == fixture_hash
    checks = receipt.get("checks", [])
    expected_cases = fixture["checks"]
    consistent = isinstance(checks, list) and len(checks) == len(expected_cases)
    if consistent:
        for check, case in zip(checks, expected_cases):
            if not isinstance(check, dict) or not isinstance(check.get("observed"), dict):
                consistent = False
                break
            if (check.get("id") != case["id"] or check.get("expected") != case["expected"]
                    or check.get("pass") is not observed_matches(check["observed"], case["expected"])):
                consistent = False
    if consistent:
        aggregate = "pass" if all(check["pass"] for check in checks) else "fail"
        validity = receipt.get("validity")
        execution = receipt.get("execution")
        consistent = (isinstance(validity, dict) and validity.get("status") == aggregate
                      and isinstance(execution, dict) and execution.get("status") == "completed"
                      and receipt.get("parameters") == fixture["parameters"]
                      and receipt.get("graph_options") == fixture["graph_options"]
                      and receipt.get("scientific_verdict") == "not_evaluated"
                      and receipt.get("baseline_reproduced") is False)
    passed = (receipt.get("schema_version") == SCHEMA and intact and matches and inputs_match
              and receipt.get("sources_stable") is True and consistent)
    return {"schema_version": SCHEMA, "kind": "receipt_verification",
            "execution": {"status": "not_run", "mode": "verify_receipt"},
            "scientific_verdict": "not_evaluated", "pass": passed,
            "receipt_integrity": intact, "current_sources_match": matches,
            "current_inputs_match": inputs_match,
            "check_results_consistent": consistent,
            "original_validity": receipt.get("validity"),
            "original_execution": receipt.get("execution"),
            "limitations": ["Revalidates identity and recorded assertions; does not rerun scoring or authenticate the producer."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code-repo", required=True, type=Path)
    parser.add_argument("--backend-repo", type=Path, help="Optional source checkout containing em_erl/")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--run", action="store_true", help="Opt in to synthetic CPU evaluator checks")
    mode.add_argument("--verify-receipt", type=Path, help="Check source/input identity and assertions without scoring")
    parser.add_argument("--receipt", type=Path, help="With --run: create a new JSON receipt; never overwrite")
    args = parser.parse_args(argv)
    if args.receipt and not args.run:
        parser.error("--receipt requires --run; inspection and verification only print JSON")
    try:
        if args.receipt and os.path.lexists(args.receipt):
            raise FileExistsError("Receipt destination already exists; refusing overwrite")
        code_repo = args.code_repo.resolve()
        if args.verify_receipt:
            result = verify_receipt(args.verify_receipt, code_repo, args.backend_repo)
            exit_code = 0 if result["pass"] else 1
        else:
            result, backend = inspect(code_repo, args.backend_repo)
            if args.run:
                result = run_checks(result, code_repo, backend)
            result["receipt_sha256"] = digest_bytes(canonical(result))
            exit_code = (0 if not args.run or result["validity"]["status"] == "pass"
                         else 2 if result["execution"]["status"] == "error" else 1)
        payload = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
        if args.receipt:
            with args.receipt.open("x", encoding="utf-8") as handle:
                handle.write(payload)
        print(payload, end="")
        return exit_code
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"schema_version": SCHEMA, "execution": {"status": "error"},
                          "validity": {"status": "unknown"}, "scientific_verdict": "not_evaluated",
                          "error": {"type": type(exc).__name__, "message": str(exc)}}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
