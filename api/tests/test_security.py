from incident_atlas.security import trusted_client_address


def test_forwarded_address_is_ignored_unless_direct_peer_is_trusted():
    assert (
        trusted_client_address(
            "203.0.113.20",
            "198.51.100.77",
            ["198.51.100.0/24"],
        )
        == "203.0.113.20"
    )


def test_trusted_proxy_chain_uses_nearest_untrusted_hop():
    assert (
        trusted_client_address(
            "198.51.100.10",
            "198.51.100.99, 203.0.113.42, 198.51.100.11",
            ["198.51.100.0/24"],
        )
        == "203.0.113.42"
    )


def test_malformed_forwarded_chain_falls_back_to_trusted_peer():
    assert (
        trusted_client_address(
            "198.51.100.10",
            "spoofed, 203.0.113.42",
            ["198.51.100.0/24"],
        )
        == "198.51.100.10"
    )
