"""Run the built demo with disposable workflow state for browser acceptance checks."""
import sys
import tempfile
from pathlib import Path
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.main import create_app

if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='northstar-review-') as folder:
        uvicorn.run(create_app(workflow_path=Path(folder)/'workflow.sqlite'), host='127.0.0.1', port=8001)
