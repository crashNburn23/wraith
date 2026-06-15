from app.services.dedup import normalise_url, url_hash
from app.services.ingest_runner import _title_tokens, _is_title_dup, _final_ingest_status
from app.services.job_state import JobRun


class TestUrlNormalisation:
    def test_strips_tracking_params(self):
        a = normalise_url("https://example.com/post?utm_source=rss&utm_medium=feed")
        b = normalise_url("https://example.com/post")
        assert a == b

    def test_case_and_trailing_slash(self):
        assert normalise_url("HTTPS://Example.COM/post/") == normalise_url("https://example.com/post")

    def test_fragment_removed(self):
        assert normalise_url("https://example.com/a#section") == normalise_url("https://example.com/a")

    def test_meaningful_params_kept(self):
        a = normalise_url("https://example.com/post?id=1")
        b = normalise_url("https://example.com/post?id=2")
        assert a != b

    def test_hash_is_stable(self):
        assert url_hash("https://example.com/x") == url_hash("https://example.com/x/")


class TestTitleDedup:
    def test_same_story_different_feeds(self):
        a = _title_tokens("Critical RCE Vulnerability Found in Apache Struts Framework")
        b = _title_tokens("Critical RCE vulnerability found in Apache Struts framework")
        assert _is_title_dup(a, [b])

    def test_different_stories(self):
        a = _title_tokens("Critical RCE Vulnerability Found in Apache Struts")
        b = _title_tokens("Ransomware Group Targets Healthcare Sector in Europe")
        assert not _is_title_dup(a, [b])

    def test_short_titles_never_dup(self):
        a = _title_tokens("Patch now")
        assert not _is_title_dup(a, [a])


class TestIngestStatus:
    def test_completed_without_source_failures(self):
        assert _final_ingest_status(JobRun(job_type="ingest", status="running")) == "completed"

    def test_partial_with_source_failures(self):
        run = JobRun(job_type="ingest", status="running", failed=3)
        assert _final_ingest_status(run) == "partial"
