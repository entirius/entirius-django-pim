# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import hashlib
import logging
import mimetypes
import os
import pathlib

import magic
from django.core.exceptions import SuspiciousFileOperation
from django.core.files import File
from django.core.files.storage import FileSystemStorage
from django.core.files.utils import validate_file_name
from django.db.models.fields.files import FieldFile, FileField

logger = logging.getLogger(__name__)


class HashedFileFieldFile(FieldFile):
    def _compute_hash(self, content):
        hash_func = hashlib.sha256()
        chunk_size = getattr(content, "DEFAULT_CHUNK_SIZE", File.DEFAULT_CHUNK_SIZE)
        for chunk in iter(lambda: content.read(chunk_size), b""):
            hash_func.update(chunk)
        return hash_func.hexdigest()

    def _guess_extension(self, file_path):
        mime = magic.from_file(file_path, mime=True)
        mime_to_ext = {
            "application/pdf": ".pdf",
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "application/msword": ".doc",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            "video/mp4": ".mp4",
        }
        if mime in mime_to_ext:
            return mime_to_ext[mime]
        ext = mimetypes.guess_extension(mime)
        return ext

    def _get_content_name(self, content):
        file_path = str(content)
        file_ext = self._guess_extension(file_path)
        file_hash = self._compute_hash(content=content)
        final_dir_name = os.path.join(file_hash[0:2], file_hash[2:4])
        final_file_name = "".join([file_hash[4:], file_ext])
        result = os.path.join(final_dir_name, final_file_name)
        return result

    def save(self, name: str, content: File, save: bool = ...) -> None:
        name_from_hash = self._get_content_name(content)
        return super().save(name_from_hash, content, save)


class HashedFileField(FileField):
    # Change attr_class so save method can be overriden
    attr_class = HashedFileFieldFile


class UniqueFileSystemStorage(FileSystemStorage):
    def save(self, name, content, max_length=None):
        """
        Skipping save if file already exists
        """
        # Get the proper name for the file, as it will actually be saved.
        if name is None:
            name = content.name

        if not hasattr(content, "chunks"):
            content = File(content, name)

        name = self.get_available_name(name, max_length=max_length)
        if self.exists(name):
            # file exists, so we're skipping save, files with same hash are the same!
            pass
        else:
            logger.info(name)
            logger.info(content)
            name = self._save(name, content)
            # Ensure that the name returned from the storage system is still valid.
            validate_file_name(name, allow_relative_path=True)
        return name

    def get_available_name(self, name, max_length=None):
        """
        Skipping checks:
          - if the filename already exists
          - max_length will not be exceeded  because its const
        """
        name = str(name).replace("\\", "/")
        dir_name, file_name = os.path.split(name)
        if ".." in pathlib.PurePath(dir_name).parts:
            raise SuspiciousFileOperation("Detected path traversal attempt in '%s'" % dir_name)
        # max_length checks
        if max_length and len(name) > max_length:
            raise Exception(f"File name in UniqueFileSystemStorage is longer than max_length={max_length}")
        validate_file_name(file_name)
        return name

    def get_alternative_name(self, file_root, file_ext):
        raise FileExistsError(f"UniqueFileSystemStorage: file already exists {file_root}{file_ext}")
