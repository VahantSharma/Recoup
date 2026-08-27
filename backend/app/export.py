"""Writes committed run artifacts for the frontend -- the Stage 1 export layer
docs/day5surfaceplan.md calls for. The standing rule this module exists to enforce
structurally, not by convention: no number reaches the screen except through a
committed artifact carrying its own manifest.

write_artifact() only ever accepts a Pydantic model instance (one of
app.export_schemas's classes) as `data`, never a raw dict -- validation happens at
construction time, inside the calling script, so a script cannot produce a malformed
artifact even by accident. See app.export_schemas's module docstring for the schema
registry.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from . import manifest as manifest_mod
from .export_schemas import ArtifactManifest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # backend/app/export.py -> repo root
FRONTEND_PUBLIC_DATA = _REPO_ROOT / "frontend" / "public" / "data"


def build_manifest(
    *,
    script: str,
    schema_name: str,
    schema_version: str,
    seed: int | dict,
    corpus_hash: str | None,
    policy_params: dict,
    simulator_params: dict,
    use_common_random_numbers: bool,
) -> ArtifactManifest:
    """Thin wrapper around app.manifest's existing git_sha()/db_path() so every
    artifact's manifest is built the same way -- never hand-assembled per script."""
    return ArtifactManifest(
        git_sha=manifest_mod.git_sha(),
        script=script,
        schema_name=schema_name,
        schema_version=schema_version,
        generated_at=datetime.now(timezone.utc),
        seed=seed,
        corpus_hash=corpus_hash,
        policy_params=policy_params,
        simulator_params=simulator_params,
        use_common_random_numbers=use_common_random_numbers,
    )


def write_artifact(
    schema_name: str,
    schema_version: str,
    manifest: ArtifactManifest,
    data: BaseModel,
    out_dir: Path = FRONTEND_PUBLIC_DATA,
) -> Path:
    """Refuses to write if the manifest's own declared schema_name/version don't match
    what was passed in explicitly -- catches a copy-paste manifest mismatch (the exact
    failure mode this file's docstring, and CLAUDE.md's DATABASE_URL/CRN precedent,
    exist to prevent) at write time, not after a screen renders stale data."""
    if manifest.schema_name != schema_name or manifest.schema_version != schema_version:
        raise ValueError(
            f"manifest declares schema_name={manifest.schema_name!r} "
            f"schema_version={manifest.schema_version!r}, but write_artifact was called "
            f"for schema_name={schema_name!r} schema_version={schema_version!r} -- these "
            "must match exactly."
        )
    envelope = {
        "schema_name": schema_name,
        "schema_version": schema_version,
        "manifest": json.loads(manifest.model_dump_json()),
        "data": json.loads(data.model_dump_json()),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{schema_name}.json"
    out_path.write_text(json.dumps(envelope, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return out_path
