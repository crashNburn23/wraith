from datetime import datetime, timezone, timedelta

from app.services.scoring import (
    _recency_factor, _profile_match, _feedback_signal,
    FeedbackContext, ACKNOWLEDGED_SIGNAL,
)
from app.services.embeddings import cosine
from app.models import Article, UserProfile


def make_article(**kw):
    a = Article(
        source_id="src",
        url=kw.get("url", "https://x.test/a"),
        url_hash=kw.get("url_hash", "h"),
        title=kw.get("title", "t"),
    )
    a.id = kw.get("id", "a1")
    a.threat_category = kw.get("threat_category")
    a.sector_targets = kw.get("sector_targets")
    a.geo_targets = kw.get("geo_targets")
    a.geo_origin = kw.get("geo_origin")
    a.ai_summary = kw.get("ai_summary")
    a.ai_severity_score = kw.get("ai_severity_score")
    a.embedding = kw.get("embedding")
    # relationship lists exist but are empty without a session
    return a


class TestRecency:
    def test_fresh_article_near_one(self):
        assert _recency_factor(datetime.now(timezone.utc), 3.0) > 0.95

    def test_half_life(self):
        three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)
        v = _recency_factor(three_days_ago, 3.0)
        assert abs(v - 0.5) < 0.01

    def test_missing_date_is_neutral(self):
        assert _recency_factor(None, 3.0) == 0.5

    def test_naive_datetime_handled(self):
        naive = datetime.now() - timedelta(days=1)
        assert 0 < _recency_factor(naive, 3.0) < 1


class TestProfileMatch:
    def test_empty_profile_scores_zero(self):
        profile = UserProfile(id=1, sectors=[], threat_actors=[], categories=[], keywords=[])
        a = make_article(threat_category="Ransomware")
        assert _profile_match(a, profile) == 0.0

    def test_category_match(self):
        profile = UserProfile(id=1, sectors=[], threat_actors=[], categories=["ransomware"], keywords=[])
        a = make_article(threat_category="Ransomware")
        assert _profile_match(a, profile) == 1.0

    def test_keyword_match_in_title(self):
        profile = UserProfile(id=1, sectors=[], threat_actors=[], categories=[], keywords=["zero-day"])
        a = make_article(title="New zero-day exploited in the wild")
        assert _profile_match(a, profile) == 1.0

    def test_watchlist_keyword_forces_full_match(self):
        profile = UserProfile(id=1, sectors=[], threat_actors=[], categories=["phishing"], keywords=[])
        a = make_article(title="VMware ESXi attacked", threat_category="Ransomware")
        ctx = FeedbackContext(watch_keywords={"vmware esxi"})
        # without watchlist: category mismatch → 0
        assert _profile_match(a, profile) == 0.0
        assert _profile_match(a, profile, ctx) == 1.0


class TestFeedbackSignal:
    def _ctx(self, rows, articles):
        ctx = FeedbackContext()
        ctx.signal_rows = rows
        ctx.past_articles = articles
        return ctx

    def test_below_min_signals_inactive(self):
        target = make_article(id="t", threat_category="Ransomware")
        past = make_article(id="p1", threat_category="Ransomware")
        now = datetime.now(timezone.utc)
        ctx = self._ctx({"p1": (1.0, now, [])}, [past])
        signal, contributors = _feedback_signal(target, ctx, min_feedback_articles=3, decay_half_life_days=30)
        assert signal == 0.0 and contributors == []

    def test_positive_overlap_raises_signal(self):
        target = make_article(id="t", threat_category="Ransomware")
        now = datetime.now(timezone.utc)
        rows, arts = {}, []
        for i in range(3):
            p = make_article(id=f"p{i}", threat_category="Ransomware")
            rows[p.id] = (1.0, now, [])
            arts.append(p)
        ctx = self._ctx(rows, arts)
        signal, contributors = _feedback_signal(target, ctx, min_feedback_articles=3, decay_half_life_days=30)
        assert signal == 1.0
        assert len(contributors) == 3

    def test_acknowledged_is_weak_positive(self):
        target = make_article(id="t", threat_category="APT")
        now = datetime.now(timezone.utc)
        rows, arts = {}, []
        for i in range(3):
            p = make_article(id=f"p{i}", threat_category="APT")
            rows[p.id] = (ACKNOWLEDGED_SIGNAL, now, [])
            arts.append(p)
        ctx = self._ctx(rows, arts)
        signal, _ = _feedback_signal(target, ctx, min_feedback_articles=3, decay_half_life_days=30)
        # weighted mean of +0.4 → (0.4+1)/2 = 0.7
        assert abs(signal - 0.7) < 0.01

    def test_no_overlap_means_no_signal(self):
        target = make_article(id="t", threat_category="DDoS")
        now = datetime.now(timezone.utc)
        rows, arts = {}, []
        for i in range(3):
            p = make_article(id=f"p{i}", threat_category="Phishing")
            rows[p.id] = (-1.0, now, [])
            arts.append(p)
        ctx = self._ctx(rows, arts)
        signal, contributors = _feedback_signal(target, ctx, min_feedback_articles=3, decay_half_life_days=30)
        assert signal == 0.0 and contributors == []

    def test_semantic_similarity_contributes(self):
        emb_a = [1.0, 0.0, 0.2]
        emb_b = [0.95, 0.05, 0.21]
        target = make_article(id="t", embedding=emb_a)
        now = datetime.now(timezone.utc)
        rows, arts = {}, []
        for i in range(3):
            p = make_article(id=f"p{i}", embedding=emb_b)
            rows[p.id] = (1.0, now, [])
            arts.append(p)
        ctx = self._ctx(rows, arts)
        signal, contributors = _feedback_signal(target, ctx, min_feedback_articles=3, decay_half_life_days=30)
        assert signal == 1.0
        assert any(r.startswith("semantic:") for c in contributors for r in c["overlap_reasons"])


class TestCosine:
    def test_identical(self):
        assert abs(cosine([1, 2, 3], [1, 2, 3]) - 1.0) < 1e-9

    def test_orthogonal(self):
        assert abs(cosine([1, 0], [0, 1])) < 1e-9

    def test_mismatched_lengths(self):
        assert cosine([1, 2], [1, 2, 3]) == 0.0

    def test_empty(self):
        assert cosine([], []) == 0.0
