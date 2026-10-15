"""Skip live provider calls unless pytest was invoked with -m live."""

import pytest


def pytest_collection_modifyitems(config, items):
    if config.getoption("-m") == "live":
        return
    skip_live = pytest.mark.skip(reason="needs a live provider; run pytest -m live")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)
