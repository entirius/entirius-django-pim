# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models


class VideoSource(models.TextChoices):
    YOUTUBE = "youtube", "YouTube"
    VIMEO = "vimeo", "Vimeo"
    UNKNOWN = "unknown", "Unknown"


class Video(models.Model):
    title = models.CharField(max_length=256, blank=True, null=True)
    is_external = models.BooleanField(default=True)
    source = models.CharField(
        choices=VideoSource.choices, blank=False, null=False, default=VideoSource.UNKNOWN, max_length=32
    )

    # Dodaje narazie tylko opcje zewnętrznego linku do video, jest ona z mozliwym null
    # ponieważ będzie mozna dodac video zapisane na dysku i sciezke do niego jak do obrazka
    # ale na razie nie jest to scope, mimo tego nie zamykam furtki

    video_url = models.URLField(max_length=256, blank=True, null=True)
    db_created = models.DateTimeField(auto_now_add=True)
    db_modified = models.DateTimeField(auto_now=True)
    objects = models.Manager()

    def get_source_label(self):
        return self.get_source_display()

    def get_source_by_url(self):
        if "youtube" in self.video_url:
            return VideoSource.YOUTUBE
        elif "vimeo" in self.video_url:
            return VideoSource.VIMEO
        return VideoSource.UNKNOWN

    def save(self, *args, **kwargs):
        if not self.source or self.source == VideoSource.UNKNOWN:
            self.source = self.get_source_by_url()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.get_source_label()}] {self.title}"

    class Meta:
        verbose_name_plural = "videos"
