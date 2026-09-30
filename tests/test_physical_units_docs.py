# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""RealProduct weight/width/height/deep declare their unit in the API schemas."""

import pytest

from django_pim.schemas.requests.product import CreateProductRequest, UpdateProductRequest
from django_pim.schemas.responses.product import ProductDetailResponse

MODELS = [CreateProductRequest, UpdateProductRequest, ProductDetailResponse]


@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.__name__)
def test_weight_names_the_mass_unit_setting(model):
    description = model.model_fields["weight"].description

    assert "DEFAULT_MASS_UNIT" in description
    assert "grams" in description


@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.__name__)
@pytest.mark.parametrize("field", ["width", "height", "deep"])
def test_dimensions_name_the_length_unit_setting(model, field):
    description = model.model_fields[field].description

    assert "DEFAULT_LENGTH_UNIT" in description
    assert "millimetres" in description


def test_model_comment_no_longer_points_at_a_missing_setting():
    import inspect

    from django_pim.models import real_product

    source = inspect.getsource(real_product)

    assert "PIM_weight_UNIT" not in source
    assert "PIM_DIMENSIONS_UNIT" not in source
