from __future__ import annotations

import math
import re
from typing import Optional

import frappe


# ---------------------------------------------------------------------------
# Common dictionaries for pattern detection
# ---------------------------------------------------------------------------

# Most common weak passwords (top 1000 subset for detection)
COMMON_PASSWORDS: set[str] = {
    "password", "123456", "12345678", "qwerty", "abc123", "monkey",
    "letmein", "dragon", "111111", "baseball", "iloveyou", "trustno1",
    "sunshine", "princess", "admin", "welcome", "shadow", "ashley",
    "football", "jesus", "michael", "ninja", "mustang", "password1",
    "123456789", "adobe123", "admin123", "login", "master", "photoshop",
    "1q2w3e4r", "zaq12wsx", "password123", "qwerty123", "lovely",
    "whatever", "starwars", "hello", "freedom", "qazwsx", "trustno1",
    "654321", "jordan", "harley", "ranger", "iwantu", "jennifer",
    "hunter", "2000", "test", "batman", "pass", "thomas", "robert",
    "access", "love", "pussy", "696969", "qwertyuiop", "maggie",
    "ou812", "rangers", "charlie", "morgan", "liverpool", "danielle",
    "jasper", "michelle", "stupid", "matthew", "andrew", "abcdef",
    "cheese", "tigger", "george", "asdfgh", "panel", "pepper",
    "hockey", "corvette", "diamond", "yellow", "golfer", "cookie",
    "martin", "chelsea", "falcon", "smokey", "booger", "yamaha",
    "soccer", "ferrari", "butter", "nicholas", "mercedes", "bulldog",
    "dakota", "cartman", "dave", "fishing", "cocacola", "carter",
    "chicken", "maverick", "snoopy", "muffin", "purple", "james",
    "banana", "matthew1", "sparky", "greenday", "steven", "miller",
    "jackson", "brandon", "cowboys", "hardcore", "samsung", "yankees",
    "joseph", "aaaaaaaa", "scooter", "orange", "gandalf", "spider",
    "melissa", "david", "money", "phoenix", "patrick", "qwer1234",
    "gateway", "knight", "thunder", "spanky", "digital", "alexander",
    "000000", "angel", "buster", "soccer1", "harley1", "christian",
    " steven", "daniel", "andrew1", "joshua", "maggie1", "william",
    "asdfasdf", "nicole", "buster1", "sunshine1", "taylor", "victoria",
    "robert1", "austin", "merlin", "rachel", "samuel", "justice",
    "comput", "amanda", "silver", "ashley1", "querty", "google",
    "golfer1", "pookie", "guitar", " jackson1", "dakota1", "cjmasterkey",
    "scorpion", "courtney", "dirty", "midnight", "cameron", "startrek",
    "boomer", "princess1", "bronco", "wildcats", "january", "sergey",
    "marina", "sarah", "apple", "anthony", "winner", "general",
    "lauren", "champion", "creative", "mercury", "dolphin", "research",
    "testing", "zxcvbnm", "porsche", "scooby", "safety", "warrior",
    "barney", "brandy", "player", "chelsea1", "raiders", "street",
    "slayer", "garfield", "apollo", "testing1", "alpha", "bond007",
    "marlboro", "tomcat", "xxx", "xxxx", "123qwe", "qwert", "snoopy1",
}

# Common keyboard sequences
KEYBOARD_SEQUENCES: list[str] = [
    "qwerty", "asdfgh", "zxcvbn", "qazwsx", "qweasd", "qwerasdf",
    "1234567890", "0987654321", "abcdefghijklmnopqrstuvwxyz",
    "zyxwvutsrqponmlkjihgfedcba", "qwertyuiop", "asdfghjkl",
    "zxcvbnm,./", "1qaz2wsx", "!qaz2wsx", "1qaz@wsx",
]

# Common date / year patterns
_YEAR_PATTERN = re.compile(r"^(19|20)\d{2}$")
_DATE_LIKE_PATTERN = re.compile(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def test_password_strength(
    password: str,
    user_inputs: Optional[list[str]] = None,
) -> dict:
    """Test password strength and return a detailed analysis.

    Implements a *zxcvbn*-like scoring system without external
    dependencies.  Considers length, character variety, common patterns,
    repetitions, sequences, and dictionary words.

    Args:
        password: The password to evaluate.
        user_inputs: Optional list of user-specific strings (name, email,
            etc.) to penalise.

    Returns:
        A dict with keys:

        - **score** (*int*): ``0`` – very weak, ``4`` – very strong.
        - **feedback** (*list[str]*): Human-readable improvement
          suggestions.
        - **crack_time_seconds** (*float*): Estimated brute-force time.
        - **crack_time_display** (*str*): Human-readable crack time.
        - **length** (*int*): Password length.
        - **uppercase_count** (*int*): Number of uppercase letters.
        - **lowercase_count** (*int*): Number of lowercase letters.
        - **digit_count** (*int*): Number of digits.
        - **special_count** (*int*): Number of special characters.
    """
    user_inputs = user_inputs or []
    password_lower = password.lower()

    # Basic character counts
    length = len(password)
    uppercase_count = sum(1 for c in password if c.isupper())
    lowercase_count = sum(1 for c in password if c.islower())
    digit_count = sum(1 for c in password if c.isdigit())
    special_count = length - uppercase_count - lowercase_count - digit_count

    # ---- Entropy estimation ----
    pool_size = 0
    if lowercase_count:
        pool_size += 26
    if uppercase_count:
        pool_size += 26
    if digit_count:
        pool_size += 10
    if special_count:
        pool_size += 32
    if pool_size == 0:
        pool_size = 1

    # Base entropy
    entropy = length * math.log2(pool_size)

    # ---- Deductions ----
    deductions = 0.0
    feedback: list[str] = []

    # 1. Length scoring
    if length < 8:
        deductions += 40
        feedback.append("Use at least 8 characters.")
    elif length < 12:
        deductions += 15
    elif length < 16:
        deductions += 5

    # 2. Character variety
    variety_score = sum([
        1 if lowercase_count else 0,
        1 if uppercase_count else 0,
        1 if digit_count else 0,
        1 if special_count else 0,
    ])
    if variety_score < 2:
        deductions += 25
        feedback.append("Add a mix of uppercase, lowercase, digits, and special characters.")
    elif variety_score < 3:
        deductions += 10
        feedback.append("Consider using more character types (uppercase, digits, symbols).")

    # 3. Common password / dictionary detection
    if password_lower in COMMON_PASSWORDS:
        deductions += 50
        feedback.append("This is a commonly used password. Choose something unique.")
    elif any(pwd in password_lower for pwd in COMMON_PASSWORDS if len(pwd) >= 4):
        deductions += 25
        feedback.append("Avoid using common words or phrases in your password.")

    # 4. User input detection
    for user_input in user_inputs:
        if user_input and len(user_input) >= 3:
            ui_lower = user_input.lower()
            if ui_lower in password_lower:
                deductions += 30
                feedback.append("Avoid using personal information in your password.")
                break

    # 5. Repetition detection
    repetition_penalty = _detect_repetition(password)
    if repetition_penalty > 0:
        deductions += repetition_penalty * 8
        feedback.append("Avoid repeating characters or patterns.")

    # 6. Sequence detection
    sequence_penalty = _detect_sequences(password_lower)
    if sequence_penalty > 0:
        deductions += sequence_penalty * 10
        feedback.append("Avoid keyboard or alphabetical sequences.")

    # 7. Year / date patterns
    if _YEAR_PATTERN.search(password):
        deductions += 10
        feedback.append("Avoid using years or dates in your password.")
    if _DATE_LIKE_PATTERN.search(password):
        deductions += 10
        feedback.append("Avoid using date-like patterns.")

    # 8. Repeated character run
    max_run = _max_consecutive_repeat(password)
    if max_run >= 3:
        deductions += (max_run - 2) * 5
        if max_run >= 3 and "repeating" not in " ".join(feedback).lower():
            feedback.append("Avoid repeating the same character multiple times.")

    # Calculate adjusted entropy
    adjusted_entropy = max(0, entropy - deductions)

    # Map to score 0-4
    if adjusted_entropy < 20:
        score = 0
    elif adjusted_entropy < 35:
        score = 1
    elif adjusted_entropy < 50:
        score = 2
    elif adjusted_entropy < 65:
        score = 3
    else:
        score = 4

    # Crack time estimation (at 10 billion guesses/second)
    guesses_per_second = 10_000_000_000
    total_combinations = 2 ** adjusted_entropy if adjusted_entropy > 0 else 1
    crack_time_seconds = total_combinations / guesses_per_second
    crack_time_display = _format_crack_time(crack_time_seconds)

    # Build feedback if empty
    if not feedback:
        if score >= 4:
            feedback.append("Excellent password!")
        elif score >= 3:
            feedback.append("Good password, but could be stronger.")
        else:
            feedback.append("Consider using a longer, more complex password.")

    return {
        "score": score,
        "feedback": feedback,
        "crack_time_seconds": crack_time_seconds,
        "crack_time_display": crack_time_display,
        "length": length,
        "uppercase_count": uppercase_count,
        "lowercase_count": lowercase_count,
        "digit_count": digit_count,
        "special_count": special_count,
        "entropy": round(adjusted_entropy, 2),
    }


def get_password_strength_feedback(score: int) -> str:
    """Return a human-readable label for a password strength *score*.

    Args:
        score: Integer score from ``0`` (very weak) to ``4`` (very strong).

    Returns:
        Descriptive label string.
    """
    labels = {
        0: "Very weak – easily guessable",
        1: "Weak – could be cracked quickly",
        2: "Fair – moderate protection",
        3: "Strong – good protection",
        4: "Very strong – excellent protection",
    }
    return labels.get(min(max(score, 0), 4), "Unknown")


def get_password_policy() -> dict:
    """Return the site's password policy requirements.

    Reads from ``System Settings`` if available, otherwise returns
    sensible defaults.

    Returns:
        Dict with keys: ``min_length``, ``min_score``,
        ``require_upper``, ``require_lower``, ``require_digit``,
        ``require_special``.
    """
    defaults = {
        "min_length": 8,
        "min_score": 2,
        "require_upper": True,
        "require_lower": True,
        "require_digit": True,
        "require_special": False,
    }

    try:
        settings = frappe.get_doc("System Settings")
        defaults["min_length"] = int(settings.get("min_password_length", 8) or 8)
        defaults["min_score"] = int(settings.get("min_password_score", 2) or 2)
        defaults["require_upper"] = bool(settings.get("password_require_upper", 1))
        defaults["require_lower"] = bool(settings.get("password_require_lower", 1))
        defaults["require_digit"] = bool(settings.get("password_require_digit", 1))
        defaults["require_special"] = bool(settings.get("password_require_special", 0))
    except Exception:
        pass

    return defaults


def check_password_against_policy(password: str) -> dict:
    """Check a password against the site's policy.

    Args:
        password: The password to check.

    Returns:
        Dict with ``valid`` (bool) and ``violations`` (list of strings).
    """
    policy = get_password_policy()
    violations: list[str] = []

    if len(password) < policy["min_length"]:
        violations.append(
            f"Password must be at least {policy['min_length']} characters long."
        )

    if policy["require_upper"] and not any(c.isupper() for c in password):
        violations.append("Password must contain at least one uppercase letter.")

    if policy["require_lower"] and not any(c.islower() for c in password):
        violations.append("Password must contain at least one lowercase letter.")

    if policy["require_digit"] and not any(c.isdigit() for c in password):
        violations.append("Password must contain at least one digit.")

    if policy["require_special"] and not any(not c.isalnum() for c in password):
        violations.append("Password must contain at least one special character.")

    strength = test_password_strength(password)
    if strength["score"] < policy["min_score"]:
        violations.append(
            f"Password strength score ({strength['score']}) is below the minimum "
            f"required ({policy['min_score']})."
        )

    return {
        "valid": len(violations) == 0,
        "violations": violations,
        "score": strength["score"],
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _detect_repetition(password: str) -> int:
    """Detect repeated character runs and return a penalty count.

    Looks for runs like ``aaa``, ``121212``, ``abab``.
    """
    penalty = 0
    length = len(password)

    # Check for repeated 2-char patterns
    for pattern_len in range(2, 4):
        for start in range(length - pattern_len * 2 + 1):
            chunk = password[start:start + pattern_len]
            next_chunk = password[start + pattern_len:start + pattern_len * 2]
            if chunk == next_chunk and len(chunk) == pattern_len:
                penalty += 1

    # Check for repeated character runs (3+ same chars)
    i = 0
    while i < length:
        j = i + 1
        while j < length and password[j] == password[i]:
            j += 1
        run = j - i
        if run >= 3:
            penalty += run - 2
        i = j

    return min(penalty, 10)


def _detect_sequences(password: str) -> int:
    """Detect keyboard and alphabetical sequences.

    Returns a penalty count based on how many sequence characters
    are found.
    """
    penalty = 0
    lower = password.lower()

    for seq in KEYBOARD_SEQUENCES:
        seq_lower = seq.lower()
        seq_len = len(seq_lower)
        for i in range(len(lower) - 2):
            substr = lower[i:i + seq_len]
            if len(substr) >= 3 and substr in seq_lower:
                penalty += len(substr) - 2

    # Detect ascending/descending digit sequences (3+)
    digit_seqs = re.findall(r'\d{3,}', lower)
    for ds in digit_seqs:
        for i in range(len(ds) - 2):
            a, b, c = int(ds[i]), int(ds[i + 1]), int(ds[i + 2])
            if (b == a + 1 and c == b + 1) or (b == a - 1 and c == b - 1):
                penalty += 1

    return min(penalty, 15)


def _max_consecutive_repeat(password: str) -> int:
    """Return the length of the longest run of identical characters."""
    max_run = 1
    current = 1
    for i in range(1, len(password)):
        if password[i] == password[i - 1]:
            current += 1
            max_run = max(max_run, current)
        else:
            current = 1
    return max_run


def _format_crack_time(seconds: float) -> str:
    """Convert seconds to a human-readable crack-time estimate."""
    if seconds < 1e-6:
        return "instant"
    if seconds < 1:
        return "less than a second"
    if seconds < 60:
        return f"{int(seconds)} seconds"
    minutes = seconds / 60
    if minutes < 60:
        return f"{int(minutes)} minutes"
    hours = minutes / 60
    if hours < 24:
        return f"{int(hours)} hours"
    days = hours / 24
    if days < 30:
        return f"{int(days)} days"
    months = days / 30
    if months < 12:
        return f"{int(months)} months"
    years = days / 365
    if years < 100:
        return f"{int(years)} years"
    if years < 1000:
        return f"{int(years)} centuries"
    return "millennia"
