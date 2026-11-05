import calendar_contract
from calendar_contract import Event


def test_test_environment_runs() -> None:
    """Verify that the test environment is configured correctly."""
    assert True


def test_shared_calendar_contract_dependency_is_available() -> None:
    """Verify the pinned shared package and its public Event export install."""
    assert calendar_contract.__version__ == "0.1.0"
    assert Event.__name__ == "Event"
