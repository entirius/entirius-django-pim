# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models


class ProductLinkToFeature(models.Model):
    """
    Product links of navigation type can optionally have,
    a feature assigned to them
    """

    link = models.ForeignKey("ProductLink", on_delete=models.CASCADE)
    feature = models.ForeignKey("Feature", on_delete=models.CASCADE)

    def save(self, *args, **kwargs):
        link_type_idx = self.link.link_type.idx if self.link.link_type else None
        if link_type_idx != "navigation":
            raise Exception("Only navigation links can be connected to features")
        else:
            super().save(*args, **kwargs)
