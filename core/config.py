"""Load the single shared configuration and apply overrides.

Why one file plus overrides: fairness (CLAUDE.md §2.3) requires every system
to read the same settings. A baseline or ablation is expressed as a small
override (a dict or a YAML file) deep-merged onto `config/default.yaml`, so a
diff of two run configs shows exactly what differs between two systems.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "config" / "default.yaml"


def deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Return a new dict: `override` merged into `base`, recursively.

    Nested mappings are merged key by key; any other value (lists included)
    in `override` replaces the value in `base`. Lists are replaced, not
    concatenated, because concatenation would make an override's effect
    depend on the base and so be harder to read in a config diff.
    """
    result = copy.deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top level of a config file must be a mapping")
    return data


def load_config(
    overrides: Iterable[Mapping[str, Any] | str | Path] = (),
    base: str | Path = DEFAULT_CONFIG,
) -> dict[str, Any]:
    """Load the base config and apply each override in order.

    An override is either a mapping or a path to a YAML file. Later overrides
    win over earlier ones.
    """
    config = _load_yaml(Path(base))
    for override in overrides:
        if isinstance(override, (str, Path)):
            override = _load_yaml(Path(override))
        config = deep_merge(config, override)
    return config


def get(config: Mapping[str, Any], dotted: str, default: Any = None) -> Any:
    """Read a nested value with a dotted path, e.g. `get(cfg, "llm.main.model")`."""
    node: Any = config
    for part in dotted.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return default
        node = node[part]
    return node


def config_hash(config: Mapping[str, Any]) -> str:
    """Stable short hash of a config, stored with every result.

    Keys are sorted so that two configs with the same content always give the
    same hash regardless of how they were built.
    """
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def flatten(config: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten nested keys to dotted paths; used to print config diffs."""
    out: dict[str, Any] = {}
    for key, value in config.items():
        path = f"{prefix}{key}"
        if isinstance(value, Mapping):
            out.update(flatten(value, path + "."))
        else:
            out[path] = value
    return out


def diff(a: Mapping[str, Any], b: Mapping[str, Any]) -> dict[str, tuple[Any, Any]]:
    """Return {dotted_key: (value_in_a, value_in_b)} for every key that differs."""
    fa, fb = flatten(a), flatten(b)
    keys = sorted(set(fa) | set(fb))
    return {k: (fa.get(k), fb.get(k)) for k in keys if fa.get(k) != fb.get(k)}
