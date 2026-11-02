BLANK = "<blank>"
def build_charset(texts, case_sensitive=True):
    chars=sorted({c for text in texts for c in (text if case_sensitive else text.lower()) if not c.isspace()})
    return [BLANK,*chars]
