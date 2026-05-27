"""Graph-memory fusion: link knowledge entries to code graph nodes."""
from pathlib import Path
from typing import Dict, List, Optional
from .storage import get_db

def link_to_graph(memory_type: str, memory_id: str, graph_node: str,
                  relationship: str = "affects",
                  project_root: Optional[Path] = None) -> None:
    db = get_db(project_root)
    try:
        db.execute("INSERT OR IGNORE INTO memory_graph_links VALUES(?,?,?,?)",
                   (memory_type, memory_id, graph_node, relationship))
        db.commit()
    except Exception: pass

def get_graph_links(memory_type: str, memory_id: str,
                    project_root: Optional[Path] = None) -> List[Dict[str, str]]:
    db = get_db(project_root)
    try:
        rows = db.execute(
            "SELECT graph_node,relationship FROM memory_graph_links WHERE memory_type=? AND memory_id=?",
            (memory_type, memory_id)).fetchall()
        return [{"node": r["graph_node"], "relationship": r["relationship"]} for r in rows]
    except Exception: return []
