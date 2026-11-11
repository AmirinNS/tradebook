import hashlib
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DENYLIST_HASHES = frozenset(
    [
        "7601db598bd5c8c44d6c3b3029a79568748fc113da3cbc3e2fb39e1d2ced29dd",
        "4b786365fbfd3a60c9328634437fd1fb9a1b14683175ee4088322454f6e4cdf8",
        "cbfc1b10bb1c2eb545b33925feb46c0420055a68417c4c2a565ba372802d36cf",
        "be1bced8eaa305f6dc2b51a0156ea70399d0c95ae9bbf0e4023dfc591f12a10b",
        "d995412c154f230675c88c0c6b964ccfb31956de458bdf14793898ea6ae5a3fa",
        "2e8b4250815a594da17424eaabfc712288db8915ca9bce1fa08e2f7ba65f726f",
        "4bfd5c0a18746aae4288d8bf755c9f93bea809e948c161325e20991a531858b5",
    ]
)

ALLOWED_EXACT_EMAILS = frozenset(
    [
        "noreply@anthropic.com",
        "user@example.com",
        "demo@example.com",
    ]
)

HOME_PATH_PATTERN = re.compile(r"/(Users|home)/[a-z]", re.IGNORECASE)
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
ALPHANUMERIC_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
COMPOUND_RUN_PATTERN = re.compile(r"[a-z0-9]+(?:[-_]+[a-z0-9]+)+")


def is_email_allowed(email: str) -> bool:
    """Return True if email is in allowlist or has an example.com domain."""
    email_lower = email.lower()
    if email_lower in ALLOWED_EXACT_EMAILS:
        return True
    parts = email_lower.split("@", 1)
    if len(parts) == 2:
        domain = parts[1]
        return domain == "example.com" or domain.endswith(".example.com")
    return False


def is_binary_file(path: Path) -> bool:
    """Return True if file contains a null byte in its first 8 KB."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
            return b"\x00" in chunk
    except OSError:
        return False


def scan_content(text: str, denylist_hashes: frozenset[str] = DENYLIST_HASHES) -> list[str]:
    """Scan text content for home paths, disallowed emails, and denylist token hashes."""
    violations = []

    # 1. Home path check
    home_match = HOME_PATH_PATTERN.search(text)
    if home_match:
        violations.append(f"Forbidden home path pattern found: {home_match.group()!r}")

    # 2. Email allowlist check
    for email in EMAIL_PATTERN.findall(text):
        if not is_email_allowed(email):
            violations.append(f"Disallowed email address found: {email!r}")

    # 3. Token hashes check
    text_lower = text.lower()
    single_tokens = ALPHANUMERIC_TOKEN_PATTERN.findall(text_lower)
    for token in single_tokens:
        h = hashlib.sha256(token.encode("utf-8")).hexdigest()
        if h in denylist_hashes:
            violations.append(f"Banned token hash matched: {h}")

    # Adjacent pairs joined without separator (e.g. foo-bar or foo_bar -> foobar)
    compound_runs = COMPOUND_RUN_PATTERN.findall(text_lower)
    for run in compound_runs:
        parts = re.split(r"[-_]+", run)
        for i in range(len(parts) - 1):
            pair = parts[i] + parts[i + 1]
            h = hashlib.sha256(pair.encode("utf-8")).hexdigest()
            if h in denylist_hashes:
                violations.append(f"Banned compound token hash matched: {h}")

    return violations


def scan_file(path: Path, denylist_hashes: frozenset[str] = DENYLIST_HASHES) -> list[str]:
    """Scan a file for clean-room violations. Returns list of violation messages."""
    if not path.is_file():
        return []
    if path.name == "uv.lock":
        return []
    if is_binary_file(path):
        return []

    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        return [f"Could not read {path}: {e}"]

    violations = scan_content(content, denylist_hashes)
    return [f"{path}: {v}" for v in violations]


def get_candidate_files(root: Path) -> list[Path]:
    """List candidate files tracked or untracked via git ls-files."""
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    paths = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line:
            paths.append(root / line)
    return paths


def test_clean_room_candidates():
    """Verify clean room across all git candidate files in the repo."""
    candidates = get_candidate_files(REPO_ROOT)
    assert len(candidates) > 0, "Candidate file list must not be empty"

    all_violations = []
    for path in candidates:
        violations = scan_file(path)
        all_violations.extend(violations)

    assert not all_violations, "Clean-room violations found:\n" + "\n".join(all_violations)


def test_clean_room_self_test(tmp_path):
    """Verify scanner accurately flags banned tokens, home paths, and disallowed emails."""
    # Extra test-only hash computed at runtime so plaintext never sits in the repo
    extra_token = "zz" + "bannedzz"
    extra_hash = hashlib.sha256(extra_token.encode("utf-8")).hexdigest()
    test_denylist = DENYLIST_HASHES | {extra_hash}

    # 1. Banned single token
    banned_file = tmp_path / "banned.txt"
    banned_file.write_text("prefix " + ("zz" + "bannedzz") + " suffix\n", encoding="utf-8")
    violations_single = scan_file(banned_file, denylist_hashes=test_denylist)
    assert any(extra_hash in v for v in violations_single), (
        f"Expected {extra_hash} in {violations_single}"
    )

    # 2. Banned compound token (hyphen)
    hyphen_file = tmp_path / "hyphen.txt"
    hyphen_file.write_text("var = 'zz" + "-bannedzz'\n", encoding="utf-8")
    violations_hyphen = scan_file(hyphen_file, denylist_hashes=test_denylist)
    assert any(extra_hash in v for v in violations_hyphen), (
        f"Expected {extra_hash} in {violations_hyphen}"
    )

    # 3. Banned compound token (underscore)
    underscore_file = tmp_path / "underscore.txt"
    underscore_file.write_text("var = 'zz" + "_bannedzz'\n", encoding="utf-8")
    violations_underscore = scan_file(underscore_file, denylist_hashes=test_denylist)
    assert any(extra_hash in v for v in violations_underscore), (
        f"Expected {extra_hash} in {violations_underscore}"
    )

    # 4. Clean control file
    clean_file = tmp_path / "clean.txt"
    clean_file.write_text(
        "Clean control text\nuser@example.com\nallowed_identifier = 42\n",
        encoding="utf-8",
    )
    assert scan_file(clean_file, denylist_hashes=test_denylist) == []

    # 5. File with home path pattern (dynamically constructed)
    home_file = tmp_path / "home.txt"
    home_file.write_text(
        "path = '" + "/" + "Users" + "/someone" + "'\n",
        encoding="utf-8",
    )
    violations_home = scan_file(home_file, denylist_hashes=test_denylist)
    assert any("Forbidden home path" in v for v in violations_home), (
        f"Expected home path flagged: {violations_home}"
    )

    # 6. File with disallowed email (dynamically constructed)
    bad_email_file = tmp_path / "bad_email.txt"
    bad_email_file.write_text(
        "email = 'disallowed" + "@" + "secret.org'\n",
        encoding="utf-8",
    )
    violations_email = scan_file(bad_email_file, denylist_hashes=test_denylist)
    assert any("Disallowed email" in v for v in violations_email), (
        f"Expected email flagged: {violations_email}"
    )

    # 7. File with allowed email addresses
    allowed_email_file = tmp_path / "allowed_email.txt"
    allowed_email_file.write_text(
        "noreply@anthropic.com\nuser@example.com\ndemo@example.com\ncustom@example.com\n",
        encoding="utf-8",
    )
    assert scan_file(allowed_email_file, denylist_hashes=test_denylist) == []
