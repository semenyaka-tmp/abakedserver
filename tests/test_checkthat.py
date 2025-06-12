import pytest
from abakedserver.utils import check_that

def test_check_that_value():
    with pytest.raises(ValueError, match="Port must be a non-negative integer"):
        check_that(-5, 'is non-negative', "Port must be a non-negative integer")

def test_check_that_type():
    with pytest.raises(ValueError, match="Unknown requirement: is ridiculous"):
        check_that(-5, 'is ridiculous', "Port must be a non-negative integer")
