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

import requests
from django.core.files import File
from django.db import IntegrityError
from PIL import Image
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .. import settings
from ..models import Picture, PictureDownloadUrl, Thumb

logger = logging.getLogger(__name__)


class PictureManager:
    ftps = {}

    class BasicAuth:
        login: str
        password: str

        def __init__(self, login: str, password: str):
            self.login = login
            self.password = password

        def auth_tuple(self) -> (str, str):
            return self.login, self.password

    def get_picture_from_url_cache(url: str):
        if not url:
            return None
        pic_url = PictureDownloadUrl.objects.filter(url=url).first()
        if pic_url is None:
            return None
        return pic_url.picture

    def set_picture_from_url(picture, url):
        # logger.info('setPictureFromUrl(picture=%s, url=%s)', picture, url)
        pic_url = PictureDownloadUrl(url=url, picture=picture)
        pic_url.save()
        return pic_url

    def download_img_to(src, dest, basic_auth: BasicAuth | None = None, verify_ssl=None):
        try:
            o = urllib.parse.urlparse(src)
        except:
            logger.error(f'Can not download picture from src="{src}"')
            return None
        if o.scheme in ("http", "https"):
            return PictureManager.download_img_to__http(src, dest, basic_auth, verify_ssl)
        if o.scheme == "ftp":
            return PictureManager.download_img_to__ftp(src, dest)
        logger.error(f'Can not download picture from src="{src}", scheme="{o.scheme}" is unsupported')
        return None

    def download_img_to__http(src, dest, basic_auth: BasicAuth | None = None, verify_ssl=None):
        # logger.info('Downloading img: %s dest: %s' % (src, dest))
        # decoding urls with unicode chars
        # ex: https://rytmy.pl/wp-content/uploads/2019/03/Twój-Weekend-e1551963025856.jpg
        parsed_link = urllib.parse.urlsplit(src)
        parsed_link = parsed_link._replace(path=urllib.parse.quote(parsed_link.path))
        encoded_link = parsed_link.geturl()
        if encoded_link != src:
            logger.info("Encoding picture url: %s => %s", src, encoded_link)
            src = encoded_link
        headers = {"User-Agent": "Mozilla/5.0"}
        kwargs = {"auth": basic_auth.auth_tuple()} if basic_auth else {}
        if verify_ssl is not None:
            kwargs["verify"] = verify_ssl

        # Make the actual request, set the timeout for no data to 10 seconds and
        # enable streaming responses, so we don't have to keep the large files in memory
        session = requests.Session()
        retry = Retry(connect=3, backoff_factor=1)
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        request = session.get(
            src, timeout=settings.TIMEOUT_PICTURE_SECONDS, stream=True, allow_redirects=True, headers=headers, **kwargs
        )
        if request.status_code not in (200, 201):
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
        PictureManager.ftps[ftp_key] = ftplib.FTP()
        PictureManager.ftps[ftp_key].encoding = "utf-8"
        PictureManager.ftps[ftp_key].connect(
            host=url_parsed.hostname,
            port=url_parsed.port,
            timeout=10,
            # source_address=None
        )
        PictureManager.ftps[ftp_key].login(
            settings.FTP_ACCOUNTS[ftp_key]["user"], settings.FTP_ACCOUNTS[ftp_key]["pass"]
        )

    def download_img_to__ftp(src, dest):
        url_parsed = urllib.parse.urlparse(src)
        if url_parsed.scheme != "ftp":
            raise Exception(f"Cos jest nie tak, spodziewalem sie url z ftp a mam: {src}")
        ftp_key = str(url_parsed.netloc)
        if ftp_key not in PictureManager.ftps:
            PictureManager._ftp_connect(url_parsed)
        path_dir, path_file = os.path.split(url_parsed.path)
        PictureManager.ftps[ftp_key].cwd(path_dir)
        logger.info(f"Downloading picture using FTP url: {src} => {dest}")
        try:
            PictureManager.ftps[ftp_key].voidcmd("NOOP")
        except OSError as e:
            logger.warning(f"FTP I/O error({e.errno}): {e.strerror}")
            PictureManager._ftp_connect(url_parsed)
        PictureManager.ftps[ftp_key].retrbinary("RETR " + path_file, open(dest, "wb").write)

    def get_thumb_by_sha(sha1):
        """
        zwraca Thumb jesli taki jest o danym sha1
        """
        assert len(sha1) == 40, "Invalid SHA1: %s" % sha1
        if Thumb.objects.filter(sha1=sha1).exists():
            thumb = Thumb.objects.get(sha1=sha1)
            return thumb
        return None

    def get_picture_by_sha(sha1):
        """
        zwraca Picture jesli taki jest o danym sha1
        """
        assert len(sha1) == 40, "Invalid SHA1: %s" % sha1
        if Picture.objects.filter(sha1=sha1).exists():
            picture = Picture.objects.get(sha1=sha1)
            return picture
        return None

    def get_picture(img_path: str, sha1=None, original_file_name=None):
        """
        zwraca Picture na podstawie pliku w img_path lub sha1
        """
        if sha1 is not None:
            picture = PictureManager.get_picture_by_sha(sha1)
            if picture is not None:
                return picture
        sha1_orig = sha1
        sha1 = hashlib.sha1(open(img_path, "rb").read()).hexdigest()
        if sha1_orig is not None and sha1_orig != sha1:
            logger.warning('SHA1 of picture "%s" is different: %s != %s' % (img_path, sha1_orig, sha1))
        if sha1 is not None:
            picture = PictureManager.get_picture_by_sha(sha1)
            if picture is not None:
                return picture

        # Validation, upewniamy sie, ze plik jest prawidlowym img w RGB
        img = Image.open(img_path)
        img.load()
        if img.mode == "CMYK":
            raise Exception(f"PIM is not accepting images in CMYK, img={img_path}")

        logger.info("Picture saving new: sha1=%s" % sha1)
        picture = Picture()
        f = open(img_path, "rb")
        try:
            try:
                picture.image.save(sha1, File(f))
                picture.original_file_name = original_file_name
                picture.save()
            except IntegrityError:
                # Czasami zdarza sie, ze rownolegle i w tym samym czasie importowane sa rozne simple produkty
                # ktore posiadaja to samo zdjecie ale o innych url
                # i wtedy get_picture_by_sha() jeszcze nie ma szans na wykrycie zapisanego, bo to sie dopiero wydarzy naraz
                picture = PictureManager.get_picture_by_sha(sha1)
                if settings.DEBUG:
                    logger.info(f"FIX: Zadzialal IntegrityError unfuckuper dla sha1={sha1}")
                assert picture is not None, (
                    f"Wystapil IntegrityError przy zapisywaniu picture, ale w bazie nie moge znalesc picture dla sha1={sha1}"
                )
        except Exception as e:
            logger.error(f'Exception while saving picture: img_path={img_path} sha1={sha1} e="{e}"')
            if settings.DEBUG:
                logger.error(f"Trace: {traceback.format_exc()}")
            picture = None
        f.close()
        return picture

    def remove_temporary_img(dest: str):
        try:
            os.remove(dest)
        except Exception:
            logger.warning("Can not remove temporary file: %s", dest)

    # return picture, is_downloaded
    def download_picture(
        download_url: str, sha1: str | None = None, basic_auth: BasicAuth | None = None, verify_ssl=None
    ):
        """
        Glowna fkcja odpowiedzialna za sciaganie, validacje, zapisanie zdjecia do db
        """
        picture = PictureManager.get_picture_from_url_cache(download_url)
        if picture is not None:
            return picture, False
        dest = os.path.join(settings.TMP_DIR, "tmp-image-%s.img" % hash(download_url))
        PictureManager.download_img_to(download_url, dest, basic_auth, verify_ssl)
        logger.info("Picture download: %s" % download_url)
        picture = PictureManager.get_picture(dest, sha1)
        if picture is None:
            return None, True
        PictureManager.remove_temporary_img(dest)
        PictureManager.set_picture_from_url(picture, download_url)
        return picture, True
