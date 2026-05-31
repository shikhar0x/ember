import re

def sanitize_filename(name: str) -> str:
    """
    Make a string safe for Linux/macOS/Windows filenames.
    """
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def normalize_title(text: str) -> str:
    """
    Strip noise from a title before scoring.
    Removes bracketed content, feat tags, and common YouTube noise words.
    """
    text = text.lower()

                                         
    text = re.sub(r"[\(\[](?:feat|ft)\.?[^\)\]]*[\)\]]", "", text, flags=re.IGNORECASE)

                                           
    text = re.sub(r"[\(\[](official\s*(video|audio|music\s*video|lyric\s*video)?|"
                  r"lyrics?|audio|hd|hq|remaster(ed)?|live|explicit|clean|"
                  r"deluxe|bonus\s*track|album\s*version|visuali[sz]er)[\)\]]",
                  "", text, flags=re.IGNORECASE)

                                 
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def normalize_artist(artists: list) -> str:
    """
    Return only the primary artist, cleaned of featured acts.
    """
    if not artists:
        return ""
    main = artists[0]
    main = re.split(
        r"\s*(?:feat\.?|ft\.?|&|,|\band\b|\bx\b)\s*",
        main,
        flags=re.IGNORECASE
    )[0]
    return main.strip().lower()