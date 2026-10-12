import shutil
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel

from vcclient_dev.server.validation_error_logging_route import ValidationErrorLoggingRoute


class UploadableFile(BaseModel):
    title: str
    filename: str


class FileuploaderInfo(BaseModel):
    uploadable_files: list[UploadableFile] = []


class FileuploaderUploadfileChunkResult(BaseModel):
    uploaded_filename: str


class FileuploaderConcatUploadedFileChunkResult(BaseModel):
    generated_filename: str


class EasyFileUploader:
    def __init__(self=None, upload_dir=None):

        self.upload_dir = upload_dir

        self.upload_dir.mkdir(exist_ok=True)

        self.info = FileuploaderInfo(
            uploadable_files=[
                UploadableFile(title="model file", filename="model_file"),
                UploadableFile(title="index file", filename="index_file"),
            ]
        )

        self.router = APIRouter()

        self.router.route_class = ValidationErrorLoggingRoute

        self.router.add_api_route("/api/uploader/info", self.get_info, methods=["GET"])

        self.router.add_api_route("/api/uploader/upload_file_chunk", self.post_upload_file_chunk, methods=["POST"])

        self.router.add_api_route(
            "/api/uploader/concat_uploaded_file_chunk", self.post_concat_uploaded_file_chunk, methods=["POST"]
        )

        self.router.add_api_route("/api_uploader_info", self.get_info, methods=["GET"])

        self.router.add_api_route("/api_uploader_upload_file_chunk", self.post_upload_file_chunk, methods=["POST"])

        self.router.add_api_route(
            "/api_uploader_concat_uploaded_file_chunk", self.post_concat_uploaded_file_chunk, methods=["POST"]
        )

    def get_info(self):

        return self.info

    def _sanitize_filename(self=None, filename=None):

        path = Path(filename)

        filename = path.name[:100]

        return filename

    def post_upload_file_chunk(self=None, file=None, filename=None, index=(File(...), Form(...), Form(...))):

        target_path = self._upload_file(self.upload_dir, file, filename, index)

        return FileuploaderUploadfileChunkResult(uploaded_filename=str(target_path))

    def _upload_file(
        self,
        upload_path=None,
        file=None,
        filename=None,
        index=("upload_path", Path, "file", UploadFile, "filename", str, "index", int),
    ):

        filename = self._sanitize_filename(filename)

        indexed_filename = f"""{filename}_{index}"""

        fileobj = file.file

        target_path = upload_path / indexed_filename

        target_file = open(target_path, "wb+")

        shutil.copyfileobj(fileobj, target_file)

        target_file.close()

        return target_path

    def post_concat_uploaded_file_chunk(self=None, filename=None, filename_chunk_num=None):

        filepath = self._concat_file_chunks(self.upload_dir, filename, filename_chunk_num)

        return FileuploaderConcatUploadedFileChunkResult(generated_filename=str(filepath))

    def _concat_file_chunks(
        self=None,
        upload_path=None,
        filename=None,
        filename_chunk_num=("upload_path", Path, "filename", str, "filename_chunk_num", int),
    ):

        filename = self._sanitize_filename(filename)

        filepath = upload_path / filename

        if filepath.exists():
            filepath.unlink()

        with open(filepath, "ab") as out:
            for i in range(filename_chunk_num):
                chunk_path = Path(f"""{filepath}_{i}""")

                chunk_file = open(chunk_path, "rb")

                out.write(chunk_file.read())

                chunk_file.close()

                chunk_path.unlink()

            out.close()

            return filepath

            with None:
                if not None:
                    pass

        return filepath
