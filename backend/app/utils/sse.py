import json


def event(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def node_enter(node_id: str, name: str) -> str:
    return event("workflow_node_enter", {"node_id": node_id, "node_name": name})


def node_leave(node_id: str, name: str) -> str:
    return event("workflow_node_leave", {"node_id": node_id, "node_name": name, "status": "done"})
