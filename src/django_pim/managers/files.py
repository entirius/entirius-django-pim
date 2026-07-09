# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import ftplib
import hashlib
import logging
import os
import traceback
import urllib
import urllib.request

import cv2
import requests
from django.core.files import File
from django.db import IntegrityError
from PIL import Image

from django_pim.models.files import FileRoleEnum, Files

from .. import settings
from ..models import Files, FilesDownloadUrl

logger = logging.getLogger(__name__)
logger_process = logging.getLogger("process")


class FilesManager:
    ftps = {}

    class BasicAuth:
        login: str
        password: str

        def __init__(self, login: str, password: str):
            self.login = login
            self.password = password

        def auth_tuple(self) -> tuple[str, str]:
            return self.login, self.password

    def get_file_from_url_cache(url: str):
        if not url:
            return None
        file_url = FilesDownloadUrl.objects.filter(url=url).first()
        if file_url is None:
            return None
        return file_url.file

    def set_file_from_url(file, url):
        file_url = FilesDownloadUrl(url=url, file=file)
        file_url.save()
        return file_url

    def download_file_to(src, dest, basic_auth: BasicAuth | None = None, safe_url_chars: str = "/"):
        try:
            o = urllib.parse.urlparse(src)
        except:
            logger.error(f'Can not download file from src="{src}"')
            return None
        if o.scheme in ("http", "https"):
            return FilesManager.download_file_to__http(src, dest, basic_auth, safe_url_chars)
        if o.scheme == "ftp":
            return FilesManager.download_file_to__ftp(src, dest)
        logger.error(f'Can not download file from src="{src}", scheme="{o.scheme}" is unsupported')
        return None

    def download_file_to__http(src, dest, basic_auth: BasicAuth | None = None, safe_url_chars: str = "/"):
        # logger.info('Downloading file: %s dest: %s' % (src, dest))
        # decoding urls with unicode chars
        # ex: https://rytmy.pl/wp-content/uploads/2019/03/Twój-Weekend-e1551963025856.jpg
        parsed_link = urllib.parse.urlsplit(src)
        # For safe_url_chars check urlib/parse.py def quote (line: 818)
        # Default char is "/". If u want more just add them in string like: "/%+()" etc
        parsed_link = parsed_link._replace(path=urllib.parse.quote(parsed_link.path, safe=safe_url_chars))
        encoded_link = parsed_link.geturl()
        if encoded_link != src:
            logger.info("Encoding file url: %s => %s", src, encoded_link)
            src = encoded_link
        headers = {"User-Agent": "Mozilla/5.0"}
        kwargs = {"auth": basic_auth.auth_tuple()} if basic_auth else {}
        # Make the actual request, set the timeout for no data to 10 seconds and
        # enable streaming responses so we don't have to keep the large files in memory
        request = requests.get(src, timeout=5, stream=True, allow_redirects=True, headers=headers, **kwargs)
        if request.status_code != 200:
            raise Exception("Error code=%s returned on request: %s" % (request.status_code, src))
        # Open the output file and make sure we write in binary mode
        with open(dest, "wb") as fh:
            # Walk through the request response in chunks of 1024 * 1024 bytes, so 1MiB
            for chunk in request.iter_content(1024 * 1024):
                # Write the chunk to the file
                fh.write(chunk)
                # Optionally we can check here if the download is taking too long
        # ustawiam headery browsera bo inaczej muna zwraca "HTTP Error 403: Forbidden"
        # opener = urllib.request.build_opener()
        # opener.addheaders = [('User-agent', 'Mozilla/5.0')]
        # urllib.request.install_opener(opener)
        # result = urllib.request.urlretrieve(src, dest)
        # return result

    def _ftp_connect(url_parsed):
        ftp_key = str(url_parsed.netloc)
        if ftp_key not in settings.FTP_ACCOUNTS:
            raise Exception(f'FTP account does not exist in settings.FTP_ACCOUNTS["{ftp_key}"]')
        FilesManager.ftps[ftp_key] = ftplib.FTP()
        FilesManager.ftps[ftp_key].encoding = "utf-8"
        FilesManager.ftps[ftp_key].connect(
            host=url_parsed.hostname,
            port=url_parsed.port,
            timeout=10,
            # source_address=None
        )
        FilesManager.ftps[ftp_key].login(settings.FTP_ACCOUNTS[ftp_key]["user"], settings.FTP_ACCOUNTS[ftp_key]["pass"])

    def download_file_to__ftp(src, dest):
        url_parsed = urllib.parse.urlparse(src)
        if url_parsed.scheme != "ftp":
            raise Exception(f"Cos jest nie tak, spodziewalem sie url z ftp a mam: {src}")
        ftp_key = str(url_parsed.netloc)
        if ftp_key not in FilesManager.ftps:
            FilesManager._ftp_connect(url_parsed)
        path_dir, path_file = os.path.split(url_parsed.path)
        FilesManager.ftps[ftp_key].cwd(path_dir)
        logger.info(f"Downloading files using FTP url: {src} => {dest}")
        try:
            FilesManager.ftps[ftp_key].voidcmd("NOOP")
        except OSError as e:
            logger.warning(f"FTP I/O error({e.errno}): {e.strerror}")
            FilesManager._ftp_connect(url_parsed)
        FilesManager.ftps[ftp_key].retrbinary("RETR " + path_file, open(dest, "wb").write)

    def get_file_by_sha(sha1):
        """
        zwraca Files jesli taki jest o danym sha1
        """
        assert len(sha1) == 40, "Invalid SHA1: %s" % sha1
        if Files.objects.filter(sha1=sha1).exists():
            product = Files.objects.get(sha1=sha1)
            return product
        return None

    def get_file(file_path: str, sha1=None, original_file_name=None, url=None, file_label=None):
        """
        zwraca Files na podstawie pliku w file_path lub sha1
        """
        if url:
            path = url
        else:
            path = file_path

        if sha1 is not None:
            file = FilesManager.get_file_by_sha(sha1)
            if file is not None:
                return file

        sha1_orig = sha1

        sha1 = hashlib.sha1()
        with open(file_path, "rb") as f:
            while True:
                data = f.read(1024)
                if not data:
                    break
                sha1.update(data)
        sha1 = sha1.hexdigest()

        if sha1_orig is not None and sha1_orig != sha1:
            logger.warning('SHA1 of file "%s" is different: %s != %s' % (file_path, sha1_orig, sha1))
        if sha1 is not None:
            file = FilesManager.get_file_by_sha(sha1)
            if file is not None:
                return file

        width, height, codec = None, None, None

        try:
            lowered_path = path.lower()
            if lowered_path.endswith(".pdf"):
                file_type = FileRoleEnum.PDF
                f = open(file_path, "rb")

            elif lowered_path.endswith(".png") or lowered_path.endswith(".jpg"):
                file_type = FileRoleEnum.PICTURE
                f = open(file_path, "rb")
                with Image.open(f) as img:
                    width, height = img.size

            elif lowered_path.endswith(".mp4"):
                file_type = FileRoleEnum.VIDEO
                video = cv2.VideoCapture(file_path)
                width = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fourcc = int(video.get(cv2.CAP_PROP_FOURCC))
                codec = "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)])
                video.release()
                f = open(file_path, errors="ignore")

            elif lowered_path.endswith(".doc") or lowered_path.endswith(".docx"):
                file_type = FileRoleEnum.DOC
                f = open(file_path, encoding="utf-8", errors="ignore")

        except FileNotFoundError:
            logger.info(f"{path} not found", extra={"details": {"file_path": path}})
        except:
            logger_process.info(f"{path} can't be opened", extra={"details": {"file_path": path}})
        file_size_bytes = os.path.getsize(file_path)
        file_size_bytes_mb = file_size_bytes / 10**6

        file = Files()
        try:
            try:
                file.file.save(sha1, File(f))
                file.width = width
                file.weight = file_size_bytes_mb
                file.height = height
                file.file_label = file_label
                file.codec = codec
                file.file_type = file_type
                file.file_path = file_path
                file.original_file_name = original_file_name
                file.sha1 = sha1
                file.save()
                logger.info("File saved new: sha1=%s" % sha1)
            except IntegrityError:
                # Czasami zdarza sie, ze rownolegle i w tym samym czasie importowane sa rozne simple produkty
                # ktore posiadaja to samo zdjecie ale o innych url
                # i wtedy get_file_by_sha() jeszcze nie ma szans na wykrycie zapisanego, bo to sie dopiero wydarzy naraz
                file = FilesManager.get_file_by_sha(sha1)
                if settings.DEBUG:
                    logger.info(f"FIX: Zadzialal IntegrityError unfuckuper dla sha1={sha1}")

                assert file is not None, (
                    f"Wystapil IntegrityError przy zapisywaniu file, ale w bazie nie moge znalesc file dla sha1={sha1}"
                )

        except Exception as e:
            logger.error(f'Exception while saving file: file_path={path} sha1={sha1} e="{e}"')
            if settings.DEBUG:
                logger.error(f"Trace: {traceback.format_exc()}")
            file = None
        f.close()
        return file

    def remove_temporary_file(dest: str):
        try:
            os.remove(dest)
        except Exception:
            logger.warning("Can not remove temporary file: %s", dest)

    def download_file(
        file_path: str,
        sha1: str | None = None,
        basic_auth: BasicAuth | None = None,
        file_label=None,
        safe_url_chars: str = "/",
    ):
        """
        Glowna fUkcja odpowiedzialna za sciaganie, validacje, zapisanie dokumentów do db
        """
        file = FilesManager.get_file_from_url_cache(file_path)
        if file is not None:
            return file, False
        dest = os.path.join(settings.TMP_DIR, "tmp-files-%s.file" % hash(file_path))
        FilesManager.download_file_to(file_path, dest, basic_auth, safe_url_chars)
        logger.info(f"File download: {file_path}")
        file = FilesManager.get_file(file_path=dest, sha1=sha1, url=file_path, file_label=file_label)
        if file is None:
            return None, True
        FilesManager.remove_temporary_file(dest)
        FilesManager.set_file_from_url(file, file_path)
        return file, True
