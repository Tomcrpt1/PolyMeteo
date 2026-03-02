from src.polymarket.markets import map_temp_to_bucket
from src.strategy.buckets import adjacent_buckets


def test_map_temp_to_bucket_edges():
    assert map_temp_to_bucket(11) == "<=12"
    assert map_temp_to_bucket(12) == "<=12"
    assert map_temp_to_bucket(13) == "13"
    assert map_temp_to_bucket(20) == ">=20"
    assert map_temp_to_bucket(24) == ">=20"


def test_adjacent_buckets():
    assert adjacent_buckets("15", radius=1) == ["14", "15", "16"]
