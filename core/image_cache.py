import requests, os, logging
from pathlib import Path
from PIL import Image
import io
from core.data import CHAMP_TFTACADEMY, ITEM_TFTACADEMY, to_tftacademy_champ, to_tftacademy_item

CDRAGON = "https://raw.communitydragon.org/latest/game"
DDRAGON = "https://ddragon.leagueoflegends.com/cdn/16.10.1"
ICONS_DIR = Path(__file__).parent.parent / "data" / "images"
ICONS_DIR.mkdir(parents=True, exist_ok=True)

REQ_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TFT-Overlay/5.0"}


def download_champion_images(force: bool = False):
    downloaded = 0
    for display_name, tfta_name in CHAMP_TFTACADEMY.items():
        sizes = [56, 32]
        for sz in sizes:
            out_path = ICONS_DIR / f"champ_TFT17_{tfta_name}_{sz}.webp"
            if out_path.exists() and not force:
                continue
            url = f"{DDRAGON}/img/champion/{tfta_name}.png"
            try:
                r = requests.get(url, headers=REQ_HEADERS, timeout=10)
                if r.status_code == 200:
                    img = Image.open(io.BytesIO(r.content)).convert("RGBA")
                    img.thumbnail((sz, sz), Image.Resampling.LANCZOS)
                    img.save(out_path, "WEBP")
                    downloaded += 1
            except Exception as e:
                logging.debug(f"Erro download champ {tfta_name} ({sz}px): {e}")
    if downloaded:
        logging.info(f"{downloaded} icones de campeao baixados (DataDragon)")


def download_item_images(force: bool = False):
    downloaded = 0
    for internal_name, cd_name in ITEM_TFTACADEMY.items():
        sizes = [32, 24]
        for sz in sizes:
            item_id = f"TFT_Item_{cd_name}"
            out_path = ICONS_DIR / f"item_{item_id}_{sz}.webp"
            if out_path.exists() and not force:
                continue
            url = f"{CDRAGON}/assets/maps/particles/tft/icons/items/{cd_name.lower()}.png"
            try:
                r = requests.get(url, headers=REQ_HEADERS, timeout=10)
                if r.status_code == 200:
                    img = Image.open(io.BytesIO(r.content)).convert("RGBA")
                    img.thumbnail((sz, sz), Image.Resampling.LANCZOS)
                    img.save(out_path, "WEBP")
                    downloaded += 1
            except Exception as e:
                logging.debug(f"Erro download item {cd_name} ({sz}px): {e}")
    if downloaded:
        logging.info(f"{downloaded} icones de item baixados")


def preload_all_images():
    logging.info("Pre-carregando imagens de CommunityDragon...")
    download_champion_images()
    download_item_images()
    logging.info("Pre-carregamento de imagens concluido")


def get_champion_icon(name: str, size: tuple = (32, 32)) -> Image.Image:
    if not name:
        return _create_placeholder(name or "?", size)
    tfta = to_tftacademy_champ(name)
    cache_path = ICONS_DIR / f"champ_TFT17_{tfta}_{size[0]}.webp"
    if cache_path.exists():
        try:
            return Image.open(cache_path).convert("RGBA").resize(size, Image.Resampling.LANCZOS)
        except Exception:
            pass
    url = f"{DDRAGON}/img/champion/{tfta}.png"
    try:
        r = requests.get(url, headers=REQ_HEADERS, timeout=10)
        if r.status_code == 200:
            img = Image.open(io.BytesIO(r.content)).convert("RGBA")
            img.thumbnail(size, Image.Resampling.LANCZOS)
            img.save(cache_path, "WEBP")
            return img
    except Exception:
        pass
    return _create_placeholder(name, size)


def get_item_icon(name: str, size: tuple = (24, 24)) -> Image.Image:
    if not name:
        return _create_placeholder("Item", size)
    tfta = to_tftacademy_item(name)
    item_id = tfta if tfta.startswith("TFT") else f"TFT_Item_{tfta}"
    cache_path = ICONS_DIR / f"item_{item_id}_{size[0]}.webp"
    if cache_path.exists():
        try:
            return Image.open(cache_path).convert("RGBA").resize(size, Image.Resampling.LANCZOS)
        except Exception:
            pass
    clean = tfta.replace("TFT_Item_", "").replace("TFT_", "")
    url = f"{CDRAGON}/assets/maps/particles/tft/icons/items/{clean.lower()}.png"
    try:
        r = requests.get(url, headers=REQ_HEADERS, timeout=10)
        if r.status_code == 200:
            img = Image.open(io.BytesIO(r.content)).convert("RGBA")
            img.thumbnail(size, Image.Resampling.LANCZOS)
            img.save(cache_path, "WEBP")
            return img
    except Exception:
        pass
    return _create_placeholder(name, size)


def _create_placeholder(text: str, size: tuple) -> Image.Image:
    from PIL import ImageDraw, ImageFont
    img = Image.new("RGBA", size, (15, 15, 20, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("consola.ttf", max(size[0] // 3, 8))
    except Exception:
        font = ImageFont.load_default()
    label = text[:2] if text else "?"
    bbox = draw.textbbox((0, 0), label, font=font)
    x = (size[0] - (bbox[2] - bbox[0])) // 2
    y = (size[1] - (bbox[3] - bbox[1])) // 2
    draw.text((x, y), label, fill=(100, 100, 110), font=font)
    return img
