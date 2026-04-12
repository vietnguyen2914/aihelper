#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def collect_items(directory: Path) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not directory.exists():
        return items
    for file in sorted(directory.glob("*.json")):
        data = load_json(file)
        if isinstance(data, dict):
            items.append(data)
        elif isinstance(data, list):
            for entry in data:
                if isinstance(entry, dict):
                    items.append(entry)
    return items


def rebuild_indexes(root: Path) -> Dict[str, Any]:
    ai_dir = root / "ai"
    features_dir = ai_dir / "features"
    flows_dir = ai_dir / "flows"
    index_dir = ai_dir / "index"

    features = collect_items(features_dir)
    flows = collect_items(flows_dir)

    feature_index_path = index_dir / "features.json"
    flow_index_path = index_dir / "flows.json"

    write_json(feature_index_path, features)
    write_json(flow_index_path, flows)

    return {
        "features_written": len(features),
        "flows_written": len(flows),
        "feature_index": str(feature_index_path.relative_to(root)),
        "flow_index": str(flow_index_path.relative_to(root)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild ai/index from ai/features and ai/flows")
    parser.add_argument("--project-root", default=None, help="Project root directory (default: cwd)")
    args = parser.parse_args()

    root = Path(args.project_root).expanduser().resolve() if args.project_root else Path.cwd().resolve()
    result = rebuild_indexes(root)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
