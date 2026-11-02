import io
import pytest
from fastapi import HTTPException
from ml_service.inference import Models, predict_derma, predict_rx, validate_image
from ml_service.main import health


def image_bytes(fmt="JPEG"):
    Image=pytest.importorskip("PIL.Image").Image
    buffer=io.BytesIO();Image.new("RGB",(80,60),(180,120,100)).save(buffer,format=fmt);return buffer.getvalue()


def test_health_reports_independent_missing_models():
    assert health()["models"]=={"derma":"missing","rx":"missing"}


def test_derma_missing_model_returns_503_after_valid_image():
    with pytest.raises(HTTPException) as error: predict_derma(Models(),None)
    assert error.value.status_code==503


def test_file_validation_status_codes():
    pytest.importorskip("PIL")
    for filename,data,expected in (("x.gif",b"gif",415),("x.jpg",b"bad",400),("x.jpg",b"x"*(10*1024*1024+1),413)):
        with pytest.raises(HTTPException) as error: validate_image(data,filename)
        assert error.value.status_code==expected


def test_segment_works_without_an_ocr_model():
    from PIL import Image
    from ml.rx.segment import segment
    blank = Image.new("RGB", (400, 200), "white")   # blank page = no words
    assert segment(blank) == []


def test_rx_predict_model_missing():
    with pytest.raises(HTTPException) as error: predict_rx(Models(),None,[])
    assert error.value.status_code==503
