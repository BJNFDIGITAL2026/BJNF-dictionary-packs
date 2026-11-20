# Allow-lists (expert-checked valid words)

`tools/verify_words.py` drops a word as a "likely misspelling" when a form that differs by one vowel length is
20x more common in both IndicCorp and Wikipedia. Some of those are real, different words (Hindi पीता "drinks" vs
पिता "father"). A word listed here skips ONLY that check; every other check still applies.
One word per line, `#` starts a comment. Add the reviewer's initials and date in a comment.
