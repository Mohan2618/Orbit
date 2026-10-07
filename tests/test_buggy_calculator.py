from buggy_calculator import add, divide, subtract


def test_add():
    assert add(10, 5) == 15


def test_divide():
    assert divide(10, 5) == 2


def test_subtract():
    assert subtract(10, 5) == 5