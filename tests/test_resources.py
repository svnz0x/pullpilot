from pullpilot.resources import resource_exists


def test_resource_exists_for_existing_file():
    assert resource_exists("config/schema.json")


def test_resource_exists_for_existing_directory():
    assert resource_exists("config")


def test_resource_exists_for_missing_resource():
    assert not resource_exists("__does_not_exist__/missing.txt")
