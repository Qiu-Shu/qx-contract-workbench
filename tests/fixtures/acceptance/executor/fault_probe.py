"""Known technical executor input; deliberately fails, never an 84-row capability."""
import pytest


@pytest.fixture
def setup_failure():
    raise ValueError('owned setup error')


@pytest.mark.parametrize('number', [1, 2, 3])
def test_pass(number):
    assert number > 0


def test_assertion_failure():
    assert False, 'owned assertion failure'


def test_setup_error(setup_failure):
    pass


@pytest.mark.skip(reason='owned unexecuted technical assertion')
def test_skipped():
    pass
