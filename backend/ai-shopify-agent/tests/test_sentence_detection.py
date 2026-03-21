"""
Test suite for FIX 5: Smart sentence boundary detection.
Ensures agent doesn't stutter on abbreviations, decimals, URLs, or ellipsis.
"""
import pytest
from app.services.voice_service import _is_sentence_boundary


def count_sentences(text: str) -> int:
    """Count how many sentence boundaries are detected in text."""
    count = 0
    for i in range(len(text)):
        if _is_sentence_boundary(text, i):
            count += 1
    return count


def test_abbreviations_no_stutter():
    """Dr. Mr. Mrs. etc. should NOT trigger sentence breaks."""
    assert count_sentences("Dr. Smith will see you now.") == 1
    assert count_sentences("Mr. and Mrs. Johnson are here.") == 1
    assert count_sentences("Prof. Williams teaches at MIT.") == 1
    assert count_sentences("The company is ABC Inc. based in NY.") == 1


def test_decimals_no_break():
    """Numbers like 19.99 or 3.14 should NOT break mid-number."""
    assert count_sentences("The price is $19.99 today.") == 1
    assert count_sentences("Pi equals 3.14159 approximately.") == 1
    assert count_sentences("Your total is $1,234.56 please.") == 1


def test_ellipsis_single_pause():
    """Ellipsis (...) marks a sentence end, then next sentence begins."""
    # "Wait..." is one sentence, "are you sure about that?" is another
    assert count_sentences("Wait... are you sure about that?") == 2
    # "I think..." "maybe..." "we should go." = 3 sentences
    assert count_sentences("I think... maybe... we should go.") == 3
    # "Hmm..." "let me check." = 2 sentences
    assert count_sentences("Hmm... let me check.") == 2


def test_urls_no_break():
    """URLs like example.com should NOT break on periods."""
    assert count_sentences("Visit example.com for details.") == 1
    assert count_sentences("Check www.site.org for more info.") == 1
    assert count_sentences("Email us at support@company.co today.") == 1


def test_multi_punctuation():
    """?! or !? should be treated as single boundary (last char counts)."""
    # "Really?!" is one sentence end, "That changes everything." is another
    assert count_sentences("Really?! That changes everything.") == 2
    assert count_sentences("What!? I can't believe it.") == 2
    assert count_sentences("Are you serious?! Tell me more.") == 2


def test_normal_sentences():
    """Regular sentences should work correctly."""
    assert count_sentences("Hello. How are you?") == 2
    assert count_sentences("I'm fine! Thanks for asking.") == 2
    assert count_sentences("What's your name? Where are you from?") == 2


def test_complex_real_world():
    """Real-world complex sentences that previously caused stuttering."""
    # Should be 1 sentence (no break after "Dr." or "19.99")
    text1 = "Dr. Smith said the price is $19.99 for the consultation."
    assert count_sentences(text1) == 1
    
    # Should be 3 sentences: "Wait..." "are you sure?" "That seems expensive."
    text2 = "Wait... are you sure? That seems expensive."
    assert count_sentences(text2) == 3
    
    # Should be 1 sentence (no break on "e.g." or "i.e.")
    text3 = "We offer many services, e.g. consulting, i.e. expert advice."
    assert count_sentences(text3) == 1


def test_edge_cases():
    """Edge cases that could break naive implementations."""
    # Empty string
    assert count_sentences("") == 0
    
    # Single character
    assert count_sentences(".") == 1
    
    # No punctuation
    assert count_sentences("Hello world") == 0
    
    # Only abbreviation
    assert count_sentences("Dr.") == 1  # End of text counts as boundary
    
    # Multiple spaces
    assert count_sentences("Hello.  World.") == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
