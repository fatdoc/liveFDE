"""Export the schemas actually declared by the composed FastAPI application."""
import json
from pathlib import Path

from live_review.main import app

root = Path(__file__).resolve().parents[2]
output = root / "docs/contracts/openapi.json"
output.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n")
print(f"Exported {len(app.openapi()['paths'])} actual route schemas to {output}")
