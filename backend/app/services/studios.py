"""Turn studio names like ["disney", "pixar"] into TMDB company ids.

TMDB's company search ranks poorly (Walt Disney Pictures is 38th for "disney"), so well-known
studios and brands come from a curated list first; anything else falls back to TMDB search.
"""

import asyncio

from app.services import tmdb
from app.services.text import normalize

# (TMDB company ids, display names, aliases). A brand can span several companies.
KNOWN_STUDIOS = [
    ([2, 6125], ["Walt Disney Pictures", "Walt Disney Animation Studios"], ["disney", "walt disney"]),
    ([6125], ["Walt Disney Animation Studios"], ["disney animation", "walt disney animation"]),
    ([3], ["Pixar"], ["pixar"]),
    ([420], ["Marvel Studios"], ["marvel", "marvel studios", "mcu"]),
    ([9993], ["DC Entertainment"], ["dc", "dc entertainment", "dc comics"]),
    ([1], ["Lucasfilm"], ["lucasfilm", "lucas film"]),
    ([174], ["Warner Bros. Pictures"], ["warner", "warner bros", "warner brothers", "wb"]),
    ([521, 7], ["DreamWorks Animation", "DreamWorks Pictures"], ["dreamworks"]),
    ([521], ["DreamWorks Animation"], ["dreamworks animation"]),
    ([33], ["Universal Pictures"], ["universal", "universal pictures"]),
    ([6704], ["Illumination"], ["illumination", "illumination entertainment"]),
    ([5, 34, 2251], ["Columbia Pictures", "Sony Pictures", "Sony Pictures Animation"], ["sony", "sony pictures"]),
    ([5], ["Columbia Pictures"], ["columbia", "columbia pictures"]),
    ([2251], ["Sony Pictures Animation"], ["sony animation", "sony pictures animation"]),
    ([4], ["Paramount Pictures"], ["paramount", "paramount pictures"]),
    ([25, 127928], ["20th Century Fox", "20th Century Studios"], ["fox", "20th century", "20th century fox", "20th century studios"]),
    ([43], ["Fox Searchlight Pictures"], ["searchlight", "fox searchlight"]),
    ([21], ["Metro-Goldwyn-Mayer"], ["mgm", "metro goldwyn mayer"]),
    ([1632, 491], ["Lionsgate", "Summit Entertainment"], ["lionsgate", "lions gate"]),
    ([12], ["New Line Cinema"], ["new line", "new line cinema"]),
    ([923], ["Legendary Pictures"], ["legendary", "legendary pictures"]),
    ([56], ["Amblin Entertainment"], ["amblin", "amblin entertainment"]),
    ([14], ["Miramax"], ["miramax"]),
    ([10146], ["Focus Features"], ["focus", "focus features"]),
    ([3172], ["Blumhouse Productions"], ["blumhouse"]),
    ([41077], ["A24"], ["a24"]),
    ([10342], ["Studio Ghibli"], ["ghibli", "studio ghibli"]),
    ([882], ["Toho"], ["toho"]),
    ([11537], ["LAIKA"], ["laika"]),
    ([297], ["Aardman"], ["aardman", "aardman animations"]),
]


GENERIC_WORDS = {"studio", "studios", "pictures", "films", "film", "productions", "entertainment", "the"}


def core(name: str) -> str:
    """'Studio Trigger' and 'TRIGGER' -> 'trigger', so generic words don't block a match."""
    words = [word for word in normalize(name).split() if word not in GENERIC_WORDS]
    return " ".join(words) or normalize(name)


_ALIASES = {alias: (ids, names) for ids, names, aliases in KNOWN_STUDIOS for alias in aliases}


async def resolve_term(term: str) -> tuple[list[int], list[str]]:
    if known := _ALIASES.get(normalize(term)):
        return known

    companies = await tmdb.search_companies(term)
    wanted = core(term)
    exact = [c for c in companies if core(c["name"]) == wanted]
    prefix = [c for c in companies if core(c["name"]).startswith(wanted)]
    chosen = exact or prefix[:3] or companies[:3]
    return [c["id"] for c in chosen], [c["name"] for c in chosen]


async def resolve(terms: list[str]) -> tuple[list[int], list[str]]:
    """Combine every term's companies, without repeats."""
    ids: list[int] = []
    names: list[str] = []
    for term_ids, term_names in await asyncio.gather(*(resolve_term(term) for term in terms)):
        for company_id, name in zip(term_ids, term_names):
            if company_id not in ids:
                ids.append(company_id)
                names.append(name)
    return ids, names
