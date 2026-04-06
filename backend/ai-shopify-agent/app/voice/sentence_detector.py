"""
Smart Sentence Boundary Detection

Handles edge cases that cause TTS stuttering:
- Abbreviations (Dr., Mr., Mrs., etc.)
- Decimals (19.99, 3.14)
- URLs (example.com)
- Ellipsis (...)
- Multi-punctuation (?!, !?)

Extracted from voice_service.py for better modularity.
"""
import logging
from typing import Set

logger = logging.getLogger(__name__)

# Common abbreviations that should NOT trigger sentence breaks
ABBREVIATIONS: Set[str] = frozenset([
    "dr", "mr", "mrs", "ms", "prof", "sr", "jr",
    "etc", "vs", "e", "g", "i", "inc", "ltd", "co",
    "st", "ave", "blvd", "dept", "est", "approx",
])

SENTENCE_ENDS: Set[str] = frozenset(".!?,")


def is_sentence_boundary(text: str, pos: int) -> bool:
    """
    Determine if position is a REAL sentence boundary.
    
    Args:
        text: Full text buffer
        pos: Character position to check
    
    Returns:
        True if this is a real sentence end, False otherwise
    
    Examples:
        >>> is_sentence_boundary("Dr. Smith is here.", 2)
        False  # "Dr." is an abbreviation
        >>> is_sentence_boundary("Dr. Smith is here.", 18)
        True   # End of sentence
        >>> is_sentence_boundary("Price is $19.99 today.", 11)
        False  # Decimal point
        >>> is_sentence_boundary("Wait... are you sure?", 7)
        True   # Last dot in ellipsis
    """
    if pos >= len(text) or text[pos] not in SENTENCE_ENDS:
        return False
    
    char = text[pos]
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Period-specific checks
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if char == '.':
        # Check for ellipsis (...) - only the LAST dot is a boundary
        dot_count = 1
        check_pos = pos + 1
        while check_pos < len(text) and text[check_pos] == '.':
            dot_count += 1
            check_pos += 1
        
        if dot_count >= 2:
            # This is part of ellipsis
            if pos + 1 < len(text) and text[pos + 1] == '.':
                return False  # Not the last dot yet
            # This IS the last dot in ellipsis - treat as boundary
        
        # Check for abbreviations (Dr., Mr., etc.)
        word_start = pos - 1
        while word_start >= 0 and text[word_start].isalpha():
            word_start -= 1
        word = text[word_start + 1:pos].lower()
        
        if word in ABBREVIATIONS:
            # Exception: if it's end of text, it IS a boundary
            if pos == len(text) - 1:
                return True
            return False
        
        # Check for decimals (19.99, 3.14)
        if pos > 0 and pos + 1 < len(text):
            if text[pos - 1].isdigit() and text[pos + 1].isdigit():
                return False
        
        # Check for URLs (example.com, www.site.org)
        if pos + 1 < len(text) and text[pos + 1].isalpha():
            # Look for domain pattern
            domain_start = max(0, word_start + 1)
            if text[domain_start:pos + 1].count('.') >= 1:
                # Likely a URL component
                return False
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Multi-punctuation checks
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if char in '!?':
        # ?! or !? - only the LAST one is a boundary
        if pos + 1 < len(text) and text[pos + 1] in '!?':
            return False  # Not the last punctuation yet
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Context checks
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    # Check if followed by capital letter or whitespace (real sentence end)
    if pos + 1 < len(text):
        next_char = text[pos + 1]
        if next_char.isspace() or next_char.isupper():
            return True
        # If next char is lowercase, probably not a sentence end
        if next_char.islower():
            return False
    
    # End of text is always a boundary
    if pos == len(text) - 1:
        return True
    
    return False


def find_sentence_boundaries(text: str) -> list[int]:
    """
    Find all sentence boundary positions in text.
    
    Args:
        text: Text to analyze
    
    Returns:
        List of character positions that are sentence boundaries
    """
    boundaries = []
    for i in range(len(text)):
        if is_sentence_boundary(text, i):
            boundaries.append(i)
    return boundaries


def split_into_sentences(text: str) -> list[str]:
    """
    Split text into sentences using smart boundary detection.
    
    Args:
        text: Text to split
    
    Returns:
        List of sentence strings
    """
    boundaries = find_sentence_boundaries(text)
    if not boundaries:
        return [text] if text else []
    
    sentences = []
    start = 0
    for boundary in boundaries:
        sentence = text[start:boundary + 1].strip()
        if sentence:
            sentences.append(sentence)
        start = boundary + 1
    
    # Add remaining text if any
    if start < len(text):
        remaining = text[start:].strip()
        if remaining:
            sentences.append(remaining)
    
    return sentences
