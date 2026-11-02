"""Test setup: run the service against an EMPTY artifacts folder,
so tests behave the same whether or not real/synthetic models are exported."""
import os
import tempfile

os.environ["ML_ARTIFACTS_DIR"] = tempfile.mkdtemp(prefix="empty_artifacts_")
os.environ.pop("ALLOW_SYNTHETIC_MODELS", None)