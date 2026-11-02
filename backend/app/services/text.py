import re


def normalize(name: str) -> str:
    """'Warner Bros.' -> 'warner bros'"""
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", name.casefold()).split())


def split_terms(query: str) -> list[str]:
    """'disney + pixar' or 'disney, pixar' -> ['disney', 'pixar']; 'alien -horror' -> ['alien', '-horror']"""
    return [term.strip() for term in re.split(r"[+,]|\s+(?=-)", query) if term.strip()]


def split_exclusions(terms: list[str]) -> tuple[list[str], list[str]]:
    """['alien', '-horror'] -> (['alien'], ['horror'])"""
    wanted = [term for term in terms if not term.startswith("-")]
    unwanted = [term.lstrip("-").strip() for term in terms if term.startswith("-")]
    return wanted, [term for term in unwanted if term]


def singular_plural(word: str) -> set[str]:
    """'alien' -> {'alien', 'aliens'}; 'aliens' -> {'aliens', 'alien'}"""
    word = normalize(word)
    return {word, word[:-1]} if word.endswith("s") else {word, word + "s"}
