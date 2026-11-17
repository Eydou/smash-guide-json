#!/usr/bin/env python3
"""Génère framedata/<index>.json à partir de ultimateframedata.com.

Usage :
    python3 -I scripts/scrape_ufd.py <dossier-cache-html> [<dossier-sortie>]

Le dossier cache reçoit les pages HTML téléchargées ; une page déjà présente
n'est pas retéléchargée, ce qui permet de relancer le parsing sans retaper le
site. La sortie par défaut est framedata/ à la racine du dépôt.

Chaque fichier est indexé par la position du personnage dans
json/characters_smash.json de l'application (le même identifiant que
douilles.json). La correspondance avec les pages UFD est codée en dur plus
bas : elle vit côté serveur pour qu'une correction n'exige pas de nouvelle
version de l'app.

Le script ne prend que les valeurs (frames, dégâts, notes). Les GIF de
hitbox restent sur ultimateframedata.com.
"""

import datetime
import json
import re
import sys
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

BASE_URL = "https://ultimateframedata.com/"
SCHEMA_VERSION = 1

# Index dans characters_smash.json -> [(slug UFD, nom de la forme)].
# Plusieurs formes pour les personnages qui ont plusieurs pages chez UFD.
ROSTER = {
    0: [("mario", "Mario")],
    1: [("donkey_kong", "Donkey Kong")],
    2: [("link", "Link")],
    3: [("samus", "Samus")],
    4: [("dark_samus", "Dark Samus")],
    5: [("yoshi", "Yoshi")],
    6: [("kirby", "Kirby")],
    7: [("fox", "Fox")],
    8: [("pikachu", "Pikachu")],
    9: [("luigi", "Luigi")],
    10: [("ness", "Ness")],
    11: [("captain_falcon", "Captain Falcon")],
    12: [("jigglypuff", "Jigglypuff")],
    13: [("peach", "Peach")],
    14: [("bowser", "Bowser")],
    15: [("ice_climbers", "Ice Climbers")],
    16: [("sheik", "Sheik")],
    17: [("zelda", "Zelda")],
    18: [("dr_mario", "Dr. Mario")],
    19: [("pichu", "Pichu")],
    20: [("falco", "Falco")],
    21: [("marth", "Marth")],
    22: [("lucina", "Lucina")],
    23: [("young_link", "Young Link")],
    24: [("ganondorf", "Ganondorf")],
    25: [("mewtwo", "Mewtwo")],
    26: [("roy", "Roy")],
    27: [("chrom", "Chrom")],
    28: [("mr_game_and_watch", "Mr. Game & Watch")],
    29: [("meta_knight", "Meta Knight")],
    30: [("pit", "Pit")],
    31: [("dark_pit", "Dark Pit")],
    32: [("zero_suit_samus", "Zero Suit Samus")],
    33: [("wario", "Wario")],
    34: [("snake", "Snake")],
    35: [("ike", "Ike")],
    36: [
        ("pt_squirtle", "Squirtle"),
        ("pt_ivysaur", "Ivysaur"),
        ("pt_charizard", "Charizard"),
    ],
    37: [("pt_squirtle", "Squirtle")],
    38: [("diddy_kong", "Diddy Kong")],
    39: [("lucas", "Lucas")],
    40: [("sonic", "Sonic")],
    41: [("king_dedede", "King Dedede")],
    42: [("olimar", "Olimar")],
    43: [("lucario", "Lucario")],
    44: [("rob", "R.O.B.")],
    45: [("toon_link", "Toon Link")],
    46: [("wolf", "Wolf")],
    47: [("villager", "Villager")],
    48: [("mega_man", "Mega Man")],
    49: [("wii_fit_trainer", "Wii Fit Trainer")],
    50: [("rosalina_and_luma", "Rosalina & Luma")],
    51: [("little_mac", "Little Mac")],
    52: [("greninja", "Greninja")],
    53: [("mii_brawler", "Mii Brawler")],
    54: [("mii_gunner", "Mii Gunner")],
    55: [("mii_swordfighter", "Mii Swordfighter")],
    56: [("palutena", "Palutena")],
    57: [("pac_man", "Pac-Man")],
    58: [("robin", "Robin")],
    59: [("shulk", "Shulk")],
    60: [("bowser_jr", "Bowser Jr.")],
    61: [("duck_hunt", "Duck Hunt")],
    62: [("ryu", "Ryu")],
    63: [("ken", "Ken")],
    64: [("cloud", "Cloud")],
    65: [("corrin", "Corrin")],
    66: [("bayonetta", "Bayonetta")],
    67: [("inkling", "Inkling")],
    68: [("ridley", "Ridley")],
    69: [("simon", "Simon")],
    70: [("richter", "Richter")],
    71: [("king_k_rool", "King K. Rool")],
    72: [("isabelle", "Isabelle")],
    73: [("incineroar", "Incineroar")],
    74: [("piranha_plant", "Piranha Plant")],
    75: [("joker", "Joker")],
    76: [("hero", "Hero")],
    77: [("banjo_and_kazooie", "Banjo & Kazooie")],
    78: [("terry", "Terry")],
    79: [("byleth", "Byleth")],
    80: [("minmin", "Min Min")],
    81: [("steve", "Steve")],
    82: [("sephiroth", "Sephiroth")],
    83: [("pyra", "Pyra"), ("mythra", "Mythra")],
    84: [("kazuya", "Kazuya")],
    85: [("sora", "Sora")],
}

# Pages UFD sans entrée dans l'application.
EXCLUDED_SLUGS = {"daisy"}

SECTIONS = {
    "groundattacks": "ground",
    # Kazuya découpe ses coups au sol en plusieurs catégories.
    "jabattacks": "ground",
    "tiltattacks": "ground",
    "crouchingattacks": "ground",
    "dashattacks": "ground",
    "smashattacks": "ground",
    "inputattacks": "ground",
    "aerialattacks": "aerial",
    "specialattacks": "special",
    "grabs": "grabs",
    "dodges": "dodges",
    "misc": "misc",
}

# Classe CSS UFD -> clé JSON.
FIELDS = {
    "startup": "startup",
    "activeframes": "active",
    "totalframes": "total",
    "landinglag": "landingLag",
    "endlag": "endlag",
    "basedamage": "damage",
    "shieldlag": "shieldLag",
    "shieldstun": "shieldStun",
    "advantage": "onShield",
    "whichhitbox": "hitbox",
    "notes": "notes",
    "hopsautocancel": "autoCancelHops",
    "hopsactionable": "actionableHops",
}
IGNORED_CLASSES = {"hitbox", "movename"}

# Olimar : une valeur par couleur de Pikmin dans les blocs « pikminbox ».
PIKMIN = {"rp": "R", "yp": "Y", "bp": "B", "wp": "W", "pp": "P"}
BLOCK_TAGS = {"div", "p", "li"}

VOID_TAGS = {"br", "img", "meta", "link", "input", "hr", "source", "wbr"}


class Node:
    def __init__(self, tag, attrs, parent):
        self.tag = tag
        self.attrs = dict(attrs)
        self.parent = parent
        self.children = []  # Node ou str

    @property
    def classes(self):
        return (self.attrs.get("class") or "").split()

    def text(self):
        parts = []

        def walk(node):
            for child in node.children:
                if isinstance(child, str):
                    parts.append(child)
                elif child.tag == "br":
                    parts.append("\n")
                elif child.tag in ("script", "style"):
                    continue
                elif child.tag in BLOCK_TAGS:
                    # Un bloc imbriqué ne doit pas coller son texte au voisin.
                    parts.append("\n")
                    walk(child)
                    parts.append("\n")
                else:
                    walk(child)

        walk(self)
        lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip()
                 for line in "".join(parts).split("\n")]
        return "\n".join(line for line in lines if line)


class TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", [], None)
        self.current = self.root

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.current)
        self.current.children.append(node)
        if tag not in VOID_TAGS:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.current.children.append(Node(tag, attrs, self.current))

    def handle_endtag(self, tag):
        if tag in VOID_TAGS:
            return
        node = self.current
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self.current = node.parent

    def handle_data(self, data):
        self.current.children.append(data)


def pikmin_text(node):
    """« Early: R -13 · Y -11 · B -16 · W -18 · P -10 », une ligne par <br>."""
    lines, current = [], []

    def flush():
        line = " ".join(part for part in current if part)
        line = re.sub(r"\s+", " ", line).replace(" ·:", ":").strip(" ·")
        if line:
            lines.append(line)
        current.clear()

    for child in node.children:
        if isinstance(child, str):
            current.append(child.strip())
        elif child.tag == "br":
            flush()
        elif child.tag == "div" and child.classes and child.classes[0] in PIKMIN:
            if current and current[-1] and not current[-1].endswith(":"):
                current.append("·")
            current.append(f"{PIKMIN[child.classes[0]]} {child.text()}")
        else:
            current.append(child.text())
    flush()
    return "\n".join(lines)


def has_nested_block(node):
    return any(
        not isinstance(child, str) and child.tag in BLOCK_TAGS
        for child in node.children
    )


def clean(value):
    if value is None:
        return None
    value = value.strip()
    if value in ("", "--", "-", "—", "N/A"):
        return None
    return value


def parse_stats(container):
    stats = []
    for child in container.children:
        if isinstance(child, str) or child.tag != "div":
            continue
        if "movename" in child.classes:
            continue
        line = child.text().replace("\n", " ")
        if not line:
            continue
        if " — " in line:
            label, value = line.split(" — ", 1)
        elif "—" in line:
            label, value = line.split("—", 1)
        else:
            label, value = line, ""
        stats.append({"label": label.strip(), "value": value.strip()})
    return stats


def parse_page(html, slug, anomalies):
    builder = TreeBuilder()
    builder.feed(html)

    sections = {key: [] for key in SECTIONS.values()}
    stats = []
    current = {"section": None}

    def visit(node):
        for child in node.children:
            if isinstance(child, str):
                continue
            if child.tag == "h2" and "movecategory" in child.classes:
                section_id = child.attrs.get("id")
                if section_id not in SECTIONS:
                    anomalies.append(f"{slug}: section inconnue {section_id!r}")
                current["section"] = SECTIONS.get(section_id)
                continue
            if child.tag == "div" and "movecontainer" in child.classes:
                handle_container(child)
                continue
            visit(child)

    def handle_container(container):
        classes = container.classes
        if "plain" in classes:
            if "misc" in classes:
                stats.extend(parse_stats(container))
            # Les autres blocs « plain » sont des introductions (Hero, Steve).
            return
        section = current["section"]
        if section is None:
            anomalies.append(f"{slug}: movecontainer hors section")
            return

        move = {}
        name = None
        for child in container.children:
            if isinstance(child, str) or child.tag != "div":
                continue
            child_classes = child.classes
            if not child_classes:
                continue
            pikmin = "pikminbox" in child_classes or any(
                not isinstance(c, str) and c.classes and c.classes[0] in PIKMIN
                for c in child.children
            )
            known = [c for c in child_classes if c in FIELDS or c == "movename"]
            if not known:
                if not set(child_classes) & IGNORED_CLASSES:
                    anomalies.append(f"{slug}: classe inconnue {child_classes!r}")
                continue
            cls = known[0]
            if cls == "movename":
                name = child.text().replace("\n", " ")
                continue
            if pikmin:
                value = clean(pikmin_text(child))
            else:
                if has_nested_block(child):
                    anomalies.append(f"{slug}/{cls}: bloc imbriqué, à vérifier")
                value = clean(child.text())
            # Olimar double certains champs : un vide, puis le détail par Pikmin.
            if value is not None:
                if FIELDS[cls] in move:
                    anomalies.append(f"{slug}/{name}: {cls} en double, écrasé")
                move[FIELDS[cls]] = value

        if not name:
            anomalies.append(f"{slug}/{section}: movecontainer sans nom")
            return
        # Sur les pummels, UFD range sa remarque sur le hitlag dans la case
        # « landing lag » : elle revient aux notes.
        landing = move.get("landingLag", "")
        if landing[:1].isalpha():
            move["notes"] = "\n".join(
                part for part in (landing, move.get("notes")) if part
            )
            del move["landingLag"]
        # Corniche, getup... : uniquement des images, rien à afficher.
        if not move:
            return
        sections[section].append({"name": name, **move})

    visit(builder.root)

    for key in ("ground", "aerial", "special", "grabs", "dodges"):
        if not sections[key]:
            anomalies.append(f"{slug}: section {key} vide")
    if not stats:
        anomalies.append(f"{slug}: pas de stats")

    return {
        "sections": [
            {"key": key, "moves": moves}
            for key, moves in sections.items()
            if moves
        ],
        "stats": stats,
    }


def download(slug, cache_dir):
    path = cache_dir / f"{slug}.html"
    if path.exists() and path.stat().st_size > 0:
        return path.read_text(encoding="utf-8")
    request = urllib.request.Request(
        BASE_URL + slug,
        headers={"User-Agent": "Mozilla/5.0 (compatible; frame-data-sync)"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        html = response.read().decode("utf-8")
    path.write_text(html, encoding="utf-8")
    time.sleep(1.5)
    return html


def check_roster_coverage(cache_dir, anomalies):
    """Toute page listée par UFD doit être mappée ou exclue volontairement."""
    index_html = download("smash", cache_dir)
    listed = set()
    for href in re.findall(r'href="/?([a-z0-9_]+)"', index_html):
        listed.add(href)
    mapped = {slug for forms in ROSTER.values() for slug, _ in forms}
    non_character = {"stats", "smash"}
    for slug in sorted(listed - mapped - EXCLUDED_SLUGS - non_character):
        anomalies.append(f"index UFD : page {slug!r} ni mappée ni exclue")
    for slug in sorted(mapped - listed):
        anomalies.append(f"mapping : {slug!r} absent de l'index UFD")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    cache_dir = Path(sys.argv[1])
    cache_dir.mkdir(parents=True, exist_ok=True)
    repo_root = Path(__file__).resolve().parent.parent
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else repo_root / "framedata"
    out_dir.mkdir(parents=True, exist_ok=True)

    anomalies = []
    check_roster_coverage(cache_dir, anomalies)

    updated = datetime.date.today().isoformat()
    parsed = {}
    for index, forms in sorted(ROSTER.items()):
        out_forms = []
        for slug, form_name in forms:
            if slug not in parsed:
                parsed[slug] = parse_page(download(slug, cache_dir), slug, anomalies)
            out_forms.append({
                "name": form_name,
                "url": BASE_URL + slug,
                **parsed[slug],
            })
        payload = {
            "schema": SCHEMA_VERSION,
            "id": index,
            "source": "ultimateframedata.com",
            "updated": updated,
            "forms": out_forms,
        }
        (out_dir / f"{index}.json").write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )

    moves = sum(
        len(section["moves"])
        for page in parsed.values()
        for section in page["sections"]
    )
    print(f"{len(ROSTER)} fichiers, {len(parsed)} pages, {moves} coups.")
    if anomalies:
        print(f"{len(anomalies)} anomalie(s) :")
        for anomaly in anomalies:
            print("  -", anomaly)


if __name__ == "__main__":
    main()
