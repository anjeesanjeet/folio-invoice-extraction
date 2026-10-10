import json

import pytest

from app.config import Settings
from app.generate import generate, printed_extraction, vendor_master
from app.llm import BaseProvider, StructuredResult

def perfect_extraction(t: dict) -> dict:
    return printed_extraction(t)


class ScriptedProvider(BaseProvider):
    name = "scripted"

    def __init__(self, results):
        super().__init__("scripted-model", 1.0, 5.0, None)
        self.results, self.calls = list(results), []

    def extract(self, system, text, images, name, schema, max_tokens=3000):
        self.calls.append((text, len(images)))
        return StructuredResult(self.results.pop(0), 2000, 400, self.cost(2000, 400))


@pytest.fixture(scope="session")
def samples(tmp_path_factory):
    d = tmp_path_factory.mktemp("samples")
    generate(d, n=10, n_hard=2)
    return d, json.loads((d / "ground_truth.json").read_text())


@pytest.fixture
def settings(tmp_path):
    s = Settings()
    s.db_path, s.storage_dir, s.outputs_dir = tmp_path / "f.db", tmp_path / "store", tmp_path / "out"
    s.vendors_path = tmp_path / "vendors.json"
    s.vendors_path.write_text(json.dumps(vendor_master()))
    return s
