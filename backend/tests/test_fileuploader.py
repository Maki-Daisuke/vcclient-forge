import io

import pytest
from starlette.testclient import TestClient

from vcclient.server.vcserver_rest_api import RestAPI


@pytest.fixture(scope="module")
def client():
    app = RestAPI.get_instance()
    return TestClient(app)


def test_fileuploader_chunk_and_concat(client, tmp_path):
    # Test uploading two chunks and concatenating them
    filename = "test_upload_file.bin"
    chunk0_data = b"Hello, "
    chunk1_data = b"World!"

    # Upload chunk 0
    res0 = client.post(
        "/api/uploader/upload_file_chunk",
        data={"filename": filename, "index": 0},
        files={"file": (filename, io.BytesIO(chunk0_data), "application/octet-stream")},
    )
    assert res0.status_code == 200, res0.text
    assert "uploaded_filename" in res0.json()

    # Upload chunk 1
    res1 = client.post(
        "/api/uploader/upload_file_chunk",
        data={"filename": filename, "index": 1},
        files={"file": (filename, io.BytesIO(chunk1_data), "application/octet-stream")},
    )
    assert res1.status_code == 200, res1.text
    assert "uploaded_filename" in res1.json()

    # Concat chunks
    res_concat = client.post(
        "/api/uploader/concat_uploaded_file_chunk",
        data={"filename": filename, "filename_chunk_num": 2},
    )
    assert res_concat.status_code == 200, res_concat.text
    concat_data = res_concat.json()
    assert "generated_filename" in concat_data
