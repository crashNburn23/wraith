from app.services.enrichment_runner import _validate_ioc, _is_valid_ip
from app.services.benign_domains import is_benign_domain


class TestIPValidation:
    def test_valid_ipv4(self):
        assert _is_valid_ip("8.8.8.8")
        assert _is_valid_ip("192.168.1.254")

    def test_defanged_ipv4(self):
        assert _is_valid_ip("1.2.3[.]4")
        assert _is_valid_ip("[1.2.3.4]")

    def test_invalid_octets_rejected(self):
        assert not _is_valid_ip("999.999.999.999")
        assert not _is_valid_ip("256.1.1.1")

    def test_garbage_rejected(self):
        assert not _is_valid_ip("not-an-ip")
        assert not _is_valid_ip("1.2.3")

    def test_ipv6(self):
        assert _is_valid_ip("2001:db8::1")


class TestIOCValidation:
    def test_valid_domain(self):
        assert _validate_ioc("domain", "evil-c2-server.xyz")

    def test_benign_domain_rejected(self):
        assert not _validate_ioc("domain", "github.com")
        assert not _validate_ioc("domain", "raw.github.com")  # subdomain
        assert not _validate_ioc("domain", "microsoft.com")

    def test_hashes(self):
        assert _validate_ioc("hash", "d41d8cd98f00b204e9800998ecf8427e")          # md5
        assert _validate_ioc("hash", "da39a3ee5e6b4b0d3255bfef95601890afd80709")  # sha1
        assert _validate_ioc("hash", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")  # sha256
        assert not _validate_ioc("hash", "nothex")
        assert not _validate_ioc("hash", "abcd1234")  # wrong length

    def test_null_and_empty_rejected(self):
        assert not _validate_ioc("domain", "null")
        assert not _validate_ioc("ip", "")

    def test_url_to_benign_site_rejected(self):
        assert not _validate_ioc("url", "https://github.com/some/repo")
        assert _validate_ioc("url", "http://evil-payload-host.ru/stage2.bin")

    def test_defanged_url(self):
        assert _validate_ioc("url", "hxxps://malicious-domain.top/payload")

    def test_email(self):
        assert _validate_ioc("email", "attacker@evil.com")
        assert not _validate_ioc("email", "not-an-email")

    def test_unknown_type_rejected(self):
        assert not _validate_ioc("filename", "evil.exe")


class TestBenignDomains:
    def test_builtin_hit(self):
        assert is_benign_domain("google.com")

    def test_subdomain_hit(self):
        assert is_benign_domain("docs.google.com")
        assert is_benign_domain("a.b.cloudflare.com")

    def test_defanged(self):
        assert is_benign_domain("github[.]com")

    def test_unknown_domain(self):
        assert not is_benign_domain("totally-evil-c2.xyz")
