"""Dados centralizados: campeoes, IDs TFT17, hex codes, itens, augments.
Source unica de verdade para todos os modulos. Evita duplicacao entre main.py, overlay.py e meta_db.py."""

# ── TFT17_ ID ↔ display name ────────────────────────────────────────────
TFT17_TO_NAME = {
    "TFT17_Aatrox": "Aatrox", "TFT17_Akali": "Akali", "TFT17_AurelionSol": "Aurelion Sol",
    "TFT17_Aurora": "Aurora", "TFT17_Bard": "Bard", "TFT17_Belveth": "Bel'Veth",
    "TFT17_Blitzcrank": "Blitzcrank", "TFT17_Briar": "Briar", "TFT17_Caitlyn": "Caitlyn",
    "TFT17_Chogath": "Cho'Gath", "TFT17_Corki": "Corki", "TFT17_Diana": "Diana",
    "TFT17_Ezreal": "Ezreal", "TFT17_Fiora": "Fiora", "TFT17_Fizz": "Fizz",
    "TFT17_Galio": "The Mighty Mech", "TFT17_Gnar": "Gnar", "TFT17_Gragas": "Gragas",
    "TFT17_Graves": "Graves", "TFT17_Gwen": "Gwen", "TFT17_Illaoi": "Illaoi",
    "TFT17_IvernMinion": "Meepsie", "TFT17_Jax": "Jax", "TFT17_Jhin": "Jhin",
    "TFT17_Jinx": "Jinx", "TFT17_Kaisa": "Kai'Sa", "TFT17_Karma": "Karma",
    "TFT17_Kindred": "Kindred", "TFT17_Leblanc": "LeBlanc", "TFT17_Leona": "Leona",
    "TFT17_Lissandra": "Lissandra", "TFT17_Lulu": "Lulu", "TFT17_Maokai": "Maokai",
    "TFT17_MasterYi": "Master Yi", "TFT17_Meepsie": "Meepsie", "TFT17_Milio": "Milio",
    "TFT17_MissFortune": "Miss Fortune", "TFT17_Mordekaiser": "Mordekaiser",
    "TFT17_Morgana": "Morgana", "TFT17_Nami": "Nami", "TFT17_Nasus": "Nasus",
    "TFT17_Nunu": "Nunu & Willump", "TFT17_Ornn": "Ornn", "TFT17_Pantheon": "Pantheon",
    "TFT17_Poppy": "Poppy", "TFT17_Pyke": "Pyke", "TFT17_Rammus": "Rammus",
    "TFT17_RekSai": "Rek'Sai", "TFT17_Rhaast": "Rhaast", "TFT17_Riven": "Riven",
    "TFT17_Samira": "Samira", "TFT17_Shen": "Shen", "TFT17_Sona": "Sona",
    "TFT17_TahmKench": "Tahm Kench", "TFT17_Talon": "Talon", "TFT17_Teemo": "Teemo",
    "TFT17_TwistedFate": "Twisted Fate", "TFT17_Urgot": "Urgot",
    "TFT17_Veigar": "Veigar", "TFT17_Vex": "Vex", "TFT17_Viktor": "Viktor",
    "TFT17_Xayah": "Xayah", "TFT17_Zed": "Zed", "TFT17_Zoe": "Zoe",
}

NAME_TO_TFT17 = {v: k for k, v in TFT17_TO_NAME.items()}

# ── Display name ↔ Portuguese ────────────────────────────────────────────
CHAMPION_PT = {
    "Aatrox": "Aatrox", "Akali": "Akali", "Aurelion Sol": "Aurelion Sol", "Aurora": "Aurora",
    "Bard": "Bard", "Bel'Veth": "Bel'Veth", "Blitzcrank": "Blitzcrank", "Briar": "Briar",
    "Caitlyn": "Caitlyn", "Cho'Gath": "Cho'Gath", "Corki": "Corki", "Diana": "Diana",
    "Apex Primordian": "Apex Primordian", "Ezreal": "Ezreal", "Fiora": "Fiora", "Fizz": "Fizz",
    "The Mighty Mech": "The Mighty Mech", "Gnar": "Gnar", "Gragas": "Gragas", "Graves": "Graves",
    "Gwen": "Gwen", "Illaoi": "Illaoi", "Meepsie": "Meepsie", "Jax": "Jax",
    "Jhin": "Jhin", "Jinx": "Jinx", "Kai'Sa": "Kai'Sa", "Karma": "Karma",
    "Kindred": "Kindred", "LeBlanc": "LeBlanc", "Leona": "Leona", "Lissandra": "Lissandra",
    "Lulu": "Lulu", "Maokai": "Maokai", "Master Yi": "Master Yi", "Milio": "Milio",
    "Miss Fortune": "Miss Fortune", "Mordekaiser": "Mordekaiser", "Morgana": "Morgana", "Nami": "Nami",
    "Nasus": "Nasus", "Nunu & Willump": "Nunu & Willump", "Ornn": "Ornn", "Pantheon": "Pantheon",
    "Poppy": "Poppy", "Pyke": "Pyke", "Rammus": "Rammus", "Rek'Sai": "Rek'Sai",
    "Rhaast": "Rhaast", "Riven": "Riven", "Samira": "Samira", "Shen": "Shen",
    "Sona": "Sona", "Tahm Kench": "Tahm Kench", "Talon": "Talon", "Teemo": "Teemo",
    "Twisted Fate": "Twisted Fate", "Urgot": "Urgot", "Veigar": "Veigar", "Vex": "Vex",
    "Viktor": "Viktor", "Xayah": "Xayah", "Zed": "Zed", "Zoe": "Zoe",
}

# Aliases para display names que podem vir com variacoes
DISPLAY_ALIASES = {
    "Belveth": "Bel'Veth", "BelVeth": "Bel'Veth",
    "Chogath": "Cho'Gath",
    "Kaisa": "Kai'Sa",
    "Leblanc": "LeBlanc",
    "RekSai": "Rek'Sai",
    "TahmKench": "Tahm Kench",
    "Nunu": "Nunu & Willump",
    "Morg": "Morgana",
    "Mighty Mech": "The Mighty Mech",
    "TwistedFate": "Twisted Fate",
    "Apex Primordian": "Apex Primordian",
}

# ── Hex codes para import code ────────────────────────────────────────────
CHAMPION_HEX = {
    "Aatrox": "01", "Akali": "02", "Aurelion Sol": "03", "Aurora": "04",
    "Bard": "05", "Bel'Veth": "06", "Blitzcrank": "07", "Briar": "08",
    "Caitlyn": "09", "Cho'Gath": "0a", "Corki": "0b", "Diana": "0c",
    "Apex Primordian": "0d", "Ezreal": "0e", "Fiora": "0f", "Fizz": "10",
    "The Mighty Mech": "11", "Gnar": "12", "Gragas": "13",
    "Graves": "14", "Gwen": "15", "Illaoi": "16", "Meepsie": "17",
    "Jax": "18", "Jhin": "19", "Jinx": "1a", "Kai'Sa": "1b",
    "Karma": "1c", "Kindred": "1d", "LeBlanc": "1e", "Leona": "1f",
    "Lissandra": "20", "Lulu": "21", "Maokai": "22", "Master Yi": "23",
    "Milio": "24", "Miss Fortune": "25", "Mordekaiser": "26", "Morgana": "27",
    "Nami": "28", "Nasus": "29", "Nunu & Willump": "2a",
    "Ornn": "2b", "Pantheon": "2c", "Poppy": "2d", "Pyke": "2e",
    "Rammus": "2f", "Rek'Sai": "30", "Rhaast": "31",
    "Riven": "32", "Samira": "33", "Shen": "34", "Sona": "35",
    "Tahm Kench": "36", "Talon": "37", "Teemo": "38",
    "Twisted Fate": "39", "Urgot": "3a",
    "Veigar": "3b", "Vex": "3c", "Viktor": "3d", "Xayah": "3e",
    "Zed": "3f", "Zoe": "40",
}

# ── TFT Academy asset names ────────────────────────────────────────────────
CHAMP_TFTACADEMY = {
    "Aatrox": "Aatrox", "Akali": "Akali", "Apex Primordian": "Enemy_Aatrox",
    "Aurelion Sol": "AurelionSol", "Aurora": "Aurora", "Bard": "Bard",
    "Bel'Veth": "Belveth", "Blitzcrank": "Blitzcrank", "Briar": "Briar",
    "Caitlyn": "Caitlyn", "Cho'Gath": "Chogath", "Corki": "Corki",
    "Diana": "Diana", "Ezreal": "Ezreal", "Fiora": "Fiora", "Fizz": "Fizz",
    "Gnar": "Gnar", "Gragas": "Gragas", "Graves": "Graves", "Gwen": "Gwen",
    "Illaoi": "Illaoi", "Jax": "Jax", "Jhin": "Jhin", "Jinx": "Jinx",
    "Kai'Sa": "Kaisa", "Karma": "Karma", "Kindred": "Kindred",
    "LeBlanc": "Leblanc", "Leona": "Leona", "Lissandra": "Lissandra",
    "Lulu": "Lulu", "Maokai": "Maokai", "Master Yi": "MasterYi",
    "Meepsie": "IvernMinion", "Milio": "Milio", "Miss Fortune": "MissFortune",
    "Mordekaiser": "Mordekaiser", "Morgana": "Morgana", "Nami": "Nami",
    "Nasus": "Nasus", "Nunu & Willump": "Nunu", "Ornn": "Ornn",
    "Pantheon": "Pantheon", "Poppy": "Poppy", "Pyke": "Pyke",
    "Rammus": "Rammus", "Rek'Sai": "RekSai", "Rhaast": "Rhaast",
    "Riven": "Riven", "Samira": "Samira", "Shen": "Shen", "Sona": "Sona",
    "Tahm Kench": "TahmKench", "Talon": "Talon", "Teemo": "Teemo",
    "The Mighty Mech": "Galio", "Twisted Fate": "TwistedFate",
    "Urgot": "Urgot", "Veigar": "Veigar", "Vex": "Vex", "Viktor": "Viktor",
    "Xayah": "Xayah", "Zed": "Zed", "Zoe": "Zoe",
}

# ── Items (internal → Portuguese) ──────────────────────────────────────────
ITEM_PT = {
    "BlueBuff": "Buff Azul", "JeweledGauntlet": "Manopla Joalheira",
    "Rabadon": "Chapéu de Rabadon", "RabadonsDeathcap": "Chapéu de Rabadon",
    "Warmogs": "Armadura de Warmog", "WarmogsArmor": "Armadura de Warmog",
    "DragonClaw": "Garra do Dragão", "DragonsClaw": "Garra do Dragão",
    "Gargoyle": "Armadura Gárgula", "GargoyleStoneplate": "Armadura Gárgula",
    "InfinityEdge": "Gume do Infinito", "IE": "Gume do Infinito",
    "RapidFireCannon": "Canhão de Repente", "RFC": "Canhão de Repente",
    "LastWhisper": "Último Sussurro",
    "Guinsoos": "Fúria de Guinsoo", "GuinsoosRageblade": "Fúria de Guinsoo",
    "Bloodthirster": "Sanguinária",
    "GiantSlayer": "Mata-Gigantes", "HandOfJustice": "Mão da Justiça",
    "ArchangelsStaff": "Cajado do Arcanjo", "Redemption": "Redenção",
    "LocketOfIronSolari": "Medalhão de Solari de Ferro",
    "LocketOfTheIronSolari": "Medalhão de Solari de Ferro",
    "FrozenHeart": "Coração Congelado", "RedBuff": "Buff Vermelho",
    "SpearOfShojin": "Lança de Shojin", "MadredsBloodrazor": "Sanguinária de Madred",
    "PowerGauntlet": "Manopla do Poder", "SteraksGage": "Manopla de Sterak",
    "GuardianAngel": "Anjo Guardião", "StatikkShiv": "Shiv Estático",
    "Deathblade": "Lâmina da Morte",
    "DarkStarEmblemItem": "Estandarte de Estrela Negra",
    "PulsefireEmblemItem": "Estandarte Fogo Pulsante",
    "ShieldTankEmblemItem": "Estandarte de Tanque de Escudo",
    "SpaceGrooveEmblemItem": "Estandarte Groove Espacial",
}

# Items (internal → TFT Academy name)
ITEM_TFTACADEMY = {
    "BlueBuff": "BlueBuff",
    "JeweledGauntlet": "JeweledGauntlet",
    "Rabadon": "RabadonsDeathcap", "RabadonsDeathcap": "RabadonsDeathcap",
    "Warmogs": "WarmogsArmor", "WarmogsArmor": "WarmogsArmor",
    "DragonClaw": "DragonsClaw", "DragonsClaw": "DragonsClaw",
    "Gargoyle": "GargoyleStoneplate", "GargoyleStoneplate": "GargoyleStoneplate",
    "InfinityEdge": "InfinityEdge", "IE": "InfinityEdge",
    "RapidFireCannon": "RapidFireCannon", "RFC": "RapidFireCannon",
    "LastWhisper": "LastWhisper",
    "Guinsoos": "GuinsoosRageblade", "GuinsoosRageblade": "GuinsoosRageblade",
    "Bloodthirster": "Bloodthirster",
    "GiantSlayer": "GiantSlayer",
    "HandOfJustice": "HandOfJustice",
    "ArchangelsStaff": "ArchangelsStaff",
    "Redemption": "Redemption",
    "LocketOfIronSolari": "LocketOfTheIronSolari", "LocketOfTheIronSolari": "LocketOfTheIronSolari",
    "FrozenHeart": "FrozenHeart",
    "RedBuff": "RedBuff",
    "SpearOfShojin": "SpearOfShojin",
    "MadredsBloodrazor": "MadredsBloodrazor",
    "PowerGauntlet": "PowerGauntlet",
    "DarkStarEmblem": "DarkStarEmblemItem", "DarkStarEmblemItem": "DarkStarEmblemItem",
    "PulsefireEmblem": "PulsefireEmblemItem", "PulsefireEmblemItem": "PulsefireEmblemItem",
    "ShieldTankEmblem": "ShieldTankEmblemItem", "ShieldTankEmblemItem": "ShieldTankEmblemItem",
    "SpaceGrooveEmblem": "SpaceGrooveEmblemItem", "SpaceGrooveEmblemItem": "SpaceGrooveEmblemItem",
    "BFSword": "BFSword", "SparringGloves": "SparringGloves",
    "TearOfTheGoddess": "TearOfTheGoddess", "RecurveBow": "RecurveBow",
    "CloakOfAgility": "CloakOfAgility", "NegatronCloak": "NegatronCloak",
    "ChainVest": "ChainVest", "GiantsBelt": "GiantsBelt",
    "NeedlesslyLargeRod": "NeedlesslyLargeRod",
    "SteraksGage": "SteraksGage", "GuardianAngel": "GuardianAngel",
    "StatikkShiv": "StatikkShiv", "Deathblade": "Deathblade",
}

# ── Augments (internal → Portuguese) ────────────────────────────────────────
AUGMENT_PT = {
    "TraitTree": "Árvore de Traits",
    "MayTheFoursBeWithYou": "Que os 4 Estejam Com Você",
    "HoldTheLine": "Segure a Linha",
    "BoxingLessons": "Aulas de Boxe",
    "Lineup": "Formação",
    "SpreadTheLove": "Espalhe o Amor",
    "TwoTanky": "Dois Tanques",
    "MakeshiftArmor": "Armadura Improvisada",
    "TreatedS2": "Tratado S2",
    "SpreadingRoots": "Raízes Espalhadas",
    "UrfsGambit": "Gambito do Urf",
}

# ── Augments (Portuguese → internal) reverse lookup ──────────────────────────
AUGMENT_PT_REVERSE = {v: k for k, v in AUGMENT_PT.items()}

def normalize_augment(name):
    """Aceita nome PT-BR ou internal, retorna internal name"""
    if not name:
        return name
    if name in AUGMENT_PT:
        return name
    return AUGMENT_PT_REVERSE.get(name, name)

# ── Funcoes de conveniencia ─────────────────────────────────────────────────

def pt(champ_name):
    """Converte TFT17_ ID ou display name para nome de exibicao canonico"""
    if not champ_name:
        return champ_name
    if champ_name.startswith("TFT17_"):
        champ_name = TFT17_TO_NAME.get(champ_name, champ_name)
    champ_name = DISPLAY_ALIASES.get(champ_name, champ_name)
    return CHAMPION_PT.get(champ_name, champ_name)

def pt_item(item_name):
    """Converte nome interno de item para portugues"""
    if not item_name:
        return item_name
    return ITEM_PT.get(item_name, item_name)

def pt_augment(aug_name):
    """Converte nome interno de augment para portugues"""
    return AUGMENT_PT.get(aug_name, aug_name)

def to_tft17(display_name):
    """Converte display name para TFT17_ ID"""
    name = DISPLAY_ALIASES.get(display_name, display_name)
    return NAME_TO_TFT17.get(name, "")

def to_tftacademy_champ(display_name):
    """Converte display name para nome de asset TFT Academy"""
    return CHAMP_TFTACADEMY.get(display_name, display_name.replace(" ", "").replace("'", "").replace("&", "").replace(".", ""))

def to_tftacademy_item(item_name):
    """Converte nome interno de item para nome TFT Academy"""
    clean = ITEM_TFTACADEMY.get(item_name, item_name.replace(" ", "").replace("'", "").replace(".", "").replace("-", ""))
    if not clean.startswith("TFT"):
        clean = f"TFT_Item_{clean}"
    return clean

def get_hex(champ_name):
    """Retorna hex code do campeao para import code"""
    return CHAMPION_HEX.get(champ_name, "00")