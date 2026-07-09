# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import hashlib
import os
from logging import getLogger

import image_transformations
from django.conf import settings
from django.core.files import File
from PIL import Image, ImageOps
from slugify import slugify

from ..managers import PictureManager
from ..models import PictureThumb, Thumb

logger = getLogger(__name__)


class PimImageResizer:
    @classmethod
    def info(cls, msg):
        logger.info(msg)

    @classmethod
    def error(cls, msg):
        logger.error(msg)

    def check_dir(path):
        if os.path.isdir(path):
            return True
        os.makedirs(path)

    def is_image(filename):
        return filename.lower().endswith((".png", ".jpg", ".gif", ".jpeg"))

    def set_extension(filename, ext="jpg"):
        base = os.path.splitext(filename)[0]
        return base + "." + ext

    def resize_fill_crop_image(
        src_path, out_path, out_x, out_y, transparency=False, merge=False, quality=70, optimize=True
    ):
        src_image = Image.open(src_path)
        resize_option = Image.ANTIALIAS
        result = src_image

        if not transparency and result.mode == "RGBA":
            new_image = Image.new("RGBA", result.size, "WHITE")
            new_image.paste(result, (0, 0), result)
            result = new_image
        if not transparency:
            result = result.convert("RGB")

        if src_image.width > out_x and src_image.height > out_y:
            result = ImageOps.fit(result, (out_x, out_y), resize_option, centering=(0.5, 0.5))
        elif src_image.width < out_x and src_image.height > out_y:
            result = ImageOps.fit(result, (src_image.width, out_y), resize_option, centering=(0.5, 0.5)).pad(
                result, (out_x, out_y), resize_option, color=(255, 255, 255), centering=(0.5, 0.5)
            )
        elif src_image.width > out_x and src_image.height < out_y:
            result = ImageOps.fit(result, (out_x, src_image.height), resize_option, centering=(0.5, 0.5)).pad(
                result, (out_x, out_y), resize_option, color=(255, 255, 255), centering=(0.5, 0.5)
            )
        else:
            result = ImageOps.pad(result, (out_x, out_y), resize_option, color=(255, 255, 255), centering=(0.5, 0.5))

        return result.save(out_path, quality=quality, optimize=optimize)

    def get_transform_method_function(transform_method: PictureThumb.TransformMethod):
        """Returns function name from image-transformation module based on string"""
        fmap = {
            PictureThumb.TransformMethod.RESIZE_RATIO_SAFE_BG_WHITE: "resize_ratio_safe_bg_white",
            PictureThumb.TransformMethod.RESIZE_RATIO_SAFE_BG_BLACK: "resize_ratio_safe_bg_black",
            PictureThumb.TransformMethod.RESIZE_RATIO_SAFE_BG_PINK: "resize_ratio_safe_bg_pink",
            PictureThumb.TransformMethod.RESIZE_RATIO_SAFE_BG_TRANSPARENT: "resize_ratio_safe_bg_transparent",
            PictureThumb.TransformMethod.RESIZE_FILL_CROP_BG_WHITE: "resize_fill_crop_bg_white",
            PictureThumb.TransformMethod.RESIZE_FILL_CROP_BG_BLACK: "resize_fill_crop_bg_black",
            PictureThumb.TransformMethod.RESIZE_FILL_CROP_BG_PINK: "resize_fill_crop_bg_pink",
            PictureThumb.TransformMethod.RESIZE_FILL_CROP_BG_TRANSPARENT: "resize_fill_crop_bg_transparent",
            PictureThumb.TransformMethod.REMOVE_BACKGROUND_EXPERIMENTAL: "remove_background_experimental",
            PictureThumb.TransformMethod.REMOVE_BACKGROUND_EXPERIMENTAL_V2: "remove_background_experimental_V2",
        }
        try:
            return fmap[transform_method]
        except Exception:
            raise Exception(f"Unsupported picture transform method: {transform_method}")

    @classmethod
    def get_thumb(
        self,
        picture,
        width=None,
        height=None,
        transform_method: PictureThumb.TransformMethod = PictureThumb.TransformMethod.RESIZE_RATIO_SAFE_BG_WHITE,
        out_format: PictureThumb.ImageFormat = PictureThumb.ImageFormat.PNG,
        quality: int = 85,
    ):
        # Check if thumb already exists
        picture_thumb = picture.picture_thumbs.filter(
            width=width, height=height, transform_method=transform_method, out_format=out_format
        ).first()
        if picture_thumb is not None:
            self.info(
                f"thumb method={transform_method}, width={width}, height={height} format={out_format} already exists for picture {picture}"
            )
            return picture_thumb.thumb
        src_path = picture.image.path
        src_sha1 = picture.sha1
        out_path_tmp = os.path.join(
            settings.TMP_DIR, f"tmp-thumb-{src_sha1}-{slugify(transform_method)}-{width}x{height}.{out_format}"
        )
        if not os.path.isfile(src_path):
            raise Exception(f"Original Picture file does not exists: path={src_path}, picture id={picture.id}")
        transform_function_name = PimImageResizer.get_transform_method_function(transform_method)
        logger.info(f"creating thumb original={src_sha1} {width}x{height} {out_format} {transform_function_name}")
        transform_function = getattr(image_transformations, transform_function_name)
        if transform_method in (
            PictureThumb.TransformMethod.RESIZE_RATIO_SAFE_BG_WHITE,
            PictureThumb.TransformMethod.RESIZE_RATIO_SAFE_BG_BLACK,
            PictureThumb.TransformMethod.RESIZE_RATIO_SAFE_BG_PINK,
            PictureThumb.TransformMethod.RESIZE_RATIO_SAFE_BG_TRANSPARENT,
            PictureThumb.TransformMethod.RESIZE_FILL_CROP_BG_WHITE,
            PictureThumb.TransformMethod.RESIZE_FILL_CROP_BG_BLACK,
            PictureThumb.TransformMethod.RESIZE_FILL_CROP_BG_PINK,
            PictureThumb.TransformMethod.RESIZE_FILL_CROP_BG_TRANSPARENT,
        ):
            transform_function(path_source=src_path, path_to=out_path_tmp, width=width, height=height, quality=quality)
        elif transform_method in (
            PictureThumb.TransformMethod.REMOVE_BACKGROUND_EXPERIMENTAL,
            PictureThumb.TransformMethod.REMOVE_BACKGROUND_EXPERIMENTAL_V2,
        ):
            transform_function(path_source=src_path, path_to=out_path_tmp)
        sha1 = hashlib.sha1(open(out_path_tmp, "rb").read()).hexdigest()
        # Check if other picture scales to the same thumb
        thumb = Thumb.objects.filter(sha1=sha1).first()
        if thumb is None:
            thumb = Thumb()
            f = open(out_path_tmp, "rb")
            thumb.image.save(sha1, File(f))  # sha1 - file name
            thumb.save()
            f.close()
        # Creating PictureThumb relation
        PictureThumb.objects.get_or_create(
            picture=picture,
            thumb=thumb,
            width=width,
            height=height,
            transform_method=transform_method,
            out_format=out_format,
        )
        PictureManager.remove_temporary_img(out_path_tmp)
        return thumb

    @classmethod
    def get_thumbs(cls, pic, config):
        """
        This func takes a Picture instance and a config.
        Config should look like this: [(width1, height1), (width2, height2) ...] or [(width1, height1, quality1), ...]
        It returns a list of Thumb instances with specified dimensions
        """
        # Generate thumbnails
        result = []
        for width, height, transform_method_str, out_format, quality in config:
            transform_method = PictureThumb.TransformMethod(transform_method_str)
            try:
                thumb = cls.get_thumb(pic, width, height, transform_method, out_format=out_format, quality=quality)
                result.append(thumb)
            except Exception as e:
                cls.error(f"{str(e)} on pic: {pic}")
        return result

    @classmethod
    def resize_pictures(cls, pictures, config):
        def print_progress(cnt, total, msg, step=1000):
            if cnt % step == 0:
                msg = f" {cnt} / {total} {msg}"
                print(msg)
                logger.info(msg)
            else:
                if step >= 1000:
                    if cnt % 10 == 0:
                        print(".", flush=True, end="")
                else:
                    print(".", flush=True, end="")

        total = len(pictures)
        cnt = 0
        for pic in pictures:
            cnt += 1
            cls.get_thumbs(pic, config)
            print_progress(cnt, total, "pictures", 1000)

    def delete_thumbs(self, pictures):
        Thumb.objects.filter(picture_thumbs__picture__in=pictures).delete()
