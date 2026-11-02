import numpy as np
import pytest
from ml.derma.config import risk_from_probabilities
from ml.rx.decode import best_path,beam_search
from ml.rx.lexicon import lexicon_correct,normalize_name

def test_derma_risk_thresholds():
    assert risk_from_probabilities([.55,.1,.1,.05,.1,.08,.02])["risk_level"]=="high"
    assert risk_from_probabilities([.1,.1,.25,.2,.05,.2,.1])["risk_level"]=="uncertain"
    assert risk_from_probabilities([.05,.05,.2,.1,.05,.5,.05])["triage_effect"]=="no_change"

def test_ctc_decoders_collapse_repeats_and_blank():
    charset=["<blank>","A","B"]
    scores=np.array([[0,5,0],[0,4,0],[5,0,0],[0,0,5]],dtype=float)
    assert best_path(scores,charset)=="AB"
    assert beam_search(np.log(np.exp(scores)/np.exp(scores).sum(axis=1,keepdims=True)),charset,beam_width=5)=="AB"

def test_lexicon_matching_and_normalization():
    assert normalize_name("Acme 500mg Tablet") == "acme"
    values=lexicon_correct("paracetmol",[{"name":"Paracetamol","normalized":"paracetamol","composition":""}],1)
    assert values[0]["name"]=="Paracetamol"
    assert values[0]["score"]>70

def test_missing_datasets_have_actionable_messages():
    from pathlib import Path
    tmp_path=Path("ml/tests/empty-data-fixture")
    from ml.derma.data import find_metadata
    from ml.rx.data_iam import read_iam
    from ml.rx.data_bd import read_bd
    with pytest.raises(FileNotFoundError,match="HAM10000 metadata") : find_metadata(tmp_path/"ham")
    with pytest.raises(FileNotFoundError,match="IAM words.txt") : read_iam(tmp_path/"iam")
    with pytest.raises(FileNotFoundError,match="No BD CSV") : read_bd(tmp_path/"bd")
