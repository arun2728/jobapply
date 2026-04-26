from jobapply.utils import normalize_ws, slugify, stable_job_id


def test_stable_job_id_stable() -> None:
    a = stable_job_id(
        site="indeed",
        company="Acme",
        title="Engineer",
        location="Remote",
        apply_url="https://example.com/apply",
        job_url="https://example.com/job",
    )
    b = stable_job_id(
        site="indeed",
        company="acme",
        title="engineer",
        location="remote",
        apply_url="https://example.com/apply",
        job_url="https://example.com/job",
    )
    assert a == b


def test_normalize_ws() -> None:
    assert normalize_ws("  A  B  ") == "a b"


def test_slugify() -> None:
    s = slugify("Senior / Dev", "Co:Inc", "abc123")
    assert "senior" in s
    assert "abc123" in s
