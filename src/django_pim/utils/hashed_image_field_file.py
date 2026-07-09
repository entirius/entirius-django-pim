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
from django.db.models.fields.files import ImageField, ImageFieldFile

logger = logging.getLogger(__name__)


class HashedImageFieldFile(ImageFieldFile):
    def _compute_hash(self, content):
        hash_func = hashlib.sha256()
        chunk_size = getattr(content, "DEFAULT_CHUNK_SIZE", File.DEFAULT_CHUNK_SIZE)
        # WARNING Make sure whole file is being read
        for chunk in iter(lambda: content.read(chunk_size), b""):
            hash_func.update(chunk)
        return hash_func.hexdigest()

    def _guess_extension(self, file_path):
        """
        WTF: mimetypes nie posiada w swojej bibliotece obslugi webp
        wtf script:
            import pprint
            import mimetypes
            pprint.pprint(mimetypes.types_map)
        """
        mime = magic.from_file(file_path, mime=True)
        mime_to_ext = {  # fix, bo mimetype nie dziala z webp
            "image/gif": ".gif",
            "image/jpeg": ".jpg",
            "image/webp": ".webp",
            "image/png": ".png",
        }
        if mime in mime_to_ext:
            return mime_to_ext[mime]
        ext = mimetypes.guess_extension(mime)
        return ext

    def _get_content_name(self, content):
        """
        This method computes name based on content.
        It needs original filename in order to keep the extension the same.
        It disregards filename and directory structure present in the name parameter.
        """
        # content is a file path
        file_path = str(content)
        file_ext = self._guess_extension(file_path)
        # Compute hash base on content
        file_hash = self._compute_hash(content=content)
        # Get final directory structure
        final_dir_name = os.path.join(file_hash[0:2], file_hash[2:4])
        # Get final file name
        final_file_name = "".join([file_hash[4:], file_ext])
        # file_ext includes the dot.
        result = os.path.join(final_dir_name, final_file_name)
        return result

    def save(self, name: str, content: File, save: bool = ...) -> None:
        """
        This method disregards the name parameter.
        This method gets called when you call instance.image.save(filename, file).
        Computes checksum for content and uses it to construct the final path to which the file will be saved.
        """
        name_from_hash = self._get_content_name(content)
        return super().save(name_from_hash, content, save)


class HashedImageField(ImageField):
    # Change attr_class so save method can be overriden
    attr_class = HashedImageFieldFile


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
            # file exists, so we are skipping save, files with same hash are the same!
            pass
        else:
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
