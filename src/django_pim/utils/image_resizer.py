# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os

from PIL import Image, ImageOps


class ImageResizer:
    def check_dir(path):
        if os.path.isdir(path):
            return True
        os.makedirs(path)

    def is_image(filename):
        return filename.lower().endswith((".png", ".jpg", ".gif", ".jpeg"))

    def set_extension(filename, ext="jpg"):
        base = os.path.splitext(filename)[0]
        return base + "." + ext

    def size_with_ratio(src_x, src_y, ratio_x, ratio_y):
        adjusted_x = round(ratio_x * src_y / ratio_y)
        adjusted_y = round(ratio_y * src_x / ratio_x)
        if adjusted_x > src_x:
            return (adjusted_x, src_y)
        elif adjusted_y > src_y:
            return (src_x, adjusted_y)
        else:
            return (src_x, src_y)

    def make_ratio(src_image, ratiox, ratioy, fill_color=(255, 255, 255, 255)):
        src_x, src_y = src_image.size
        out_x, out_y = ImageResizer.size_with_ratio(src_x, src_y, ratiox, ratioy)
        if src_image.mode == "RGBA":
            # niszcze transparency i dodaje biale tlo
            background = Image.new("RGBA", src_image.size, (255, 255, 255))
            src_image = Image.alpha_composite(background, src_image)
        out_image = Image.new("RGB", (out_x, out_y), fill_color)
        out_image.paste(src_image, (round((out_x - src_x) / 2), round((out_y - src_y) / 2)))
        return out_image

    def size_to_size_with_ratio(src_x, src_y, out_x, out_y):
        ratio_x = out_x / src_x
        ratio_y = out_y / src_y
        if ratio_x > ratio_y:
            resize_ratio = ratio_y
            resized_y = out_y
            resized_x = round(src_x * resize_ratio)
        else:
            resize_ratio = ratio_x
            resized_x = out_x
            resized_y = round(src_y * resize_ratio)
        return (resized_x, resized_y)

    def resize_image_to_ratio(src_path, out_path, ratiox, ratioy):
        src_image = Image.open(src_path)
        out_image = ImageResizer.make_ratio(src_image, ratiox, ratioy)
        out_image = out_image.convert("RGB")
        out_image.save(out_path, quality=90)

    def resize_image_ratio_safe(
        src_path, out_path, out_x, out_y, fill_color=(255, 255, 255, 255), quality=75, optimize=True
    ):
        src_image = Image.open(src_path)
        src_x, src_y = src_image.size
        if src_x == out_x and src_y == out_y:
            return src_image.save(out_path, quality=quality, optimize=optimize)

        resized_x, resized_y = ImageResizer.size_to_size_with_ratio(src_x, src_y, out_x, out_y)
        resized_image = src_image.resize((resized_x, resized_y), Image.ANTIALIAS)
        out_image = ImageResizer.make_ratio(resized_image, out_x, out_y)
        out_image = out_image.convert("RGB")
        return out_image.save(out_path, quality=quality, optimize=optimize)

    def resize_fill_crop_image(src_path, out_path, out_x, out_y, transparency=False, quality=75, optimize=True):
        src_image = Image.open(src_path)
        resize_option = Image.ANTIALIAS
        result = src_image

        if not transparency and result.mode == "RGBA":
            new_image = Image.new("RGBA", result.size, "WHITE")
            new_image.paste(result, (0, 0), result)
            result = new_image
        if not transparency:
            result = result.convert("RGB")

        if src_image.width > out_x:
            result = ImageOps.fit(result, (out_x, result.height), resize_option, centering=(0.5, 0.5))
        else:
            result = ImageOps.pad(
                result, (out_x, result.height), resize_option, color=(255, 255, 255), centering=(0.5, 0.5)
            )
        if src_image.height > out_y:
            result = ImageOps.fit(result, (result.width, out_y), resize_option, centering=(0.5, 0.5))
        else:
            result = ImageOps.pad(
                result, (result.width, out_y), resize_option, color=(255, 255, 255), centering=(0.5, 0.5)
            )

        return result.save(out_path, quality=quality, optimize=optimize)
