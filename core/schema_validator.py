"""Validador de schema para todos os JSONs de data/ com auto-repair"""
import json, logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List

DATA_DIR = Path(__file__).parent.parent / "data"

SCHEMAS = {
    "meta_db.json": {
        "required_keys": ["comps"],
        "comp_required": ["units", "tier"],
        "optional_keys": ["last_updated", "source", "ranks_analyzed"],
    },
    "opponent_state.json": {
        "required_keys": [],  # Pode ser vazio ou dict de oponentes
        "is_dict": True,
    },
    "api_cache.json": {
        "required_keys": [],
        "is_dict": True,
    },
    "riot_key_state.json": {
        "required_keys": ["created_at", "expires_at", "status"],
    },
}


def _repair_meta_db():
    """Regenera meta_db.json com dados hardcoded"""
    from core.meta_db import MetaDB
    logging.warning("Auto-repair: regenerando meta_db.json com dados hardcoded")
    meta = MetaDB()
    data = {
        "comps": meta.data["comps"],
        "last_updated": datetime.now().isoformat(),
        "source": "auto-repair-hardcoded",
        "ranks_analyzed": []
    }
    filepath = DATA_DIR / "meta_db.json"
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return True


def _repair_opponent_state():
    """Regenera opponent_state.json vazio"""
    logging.warning("Auto-repair: regenerando opponent_state.json vazio")
    filepath = DATA_DIR / "opponent_state.json"
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump({"opponents": []}, f, indent=2)
    return True


def _repair_api_cache():
    """Regenera api_cache.json vazio"""
    logging.warning("Auto-repair: regenerando api_cache.json vazio")
    filepath = DATA_DIR / "api_cache.json"
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump({}, f, indent=2)
    return True


def _repair_riot_key_state():
    """Regenera riot_key_state.json com defaults"""
    logging.warning("Auto-repair: regenerando riot_key_state.json com defaults")
    filepath = DATA_DIR / "riot_key_state.json"
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump({
            "created_at": datetime.now().isoformat(),
            "expires_at": datetime.now().isoformat(),
            "status": "unknown"
        }, f, indent=2)
    return True


REPAIR_FUNCTIONS = {
    "meta_db.json": _repair_meta_db,
    "opponent_state.json": _repair_opponent_state,
    "api_cache.json": _repair_api_cache,
    "riot_key_state.json": _repair_riot_key_state,
}


def validate_json_file(filename: str) -> Dict:
    """Valida um arquivo JSON contra seu schema"""
    filepath = DATA_DIR / filename
    result = {
        "valid": False,
        "file": filename,
        "missing_keys": [],
        "fallback_triggered": False,
        "repaired": False,
        "error": None
    }
    
    schema = SCHEMAS.get(filename)
    if not schema:
        result["error"] = "Schema nao definido"
        return result
    
    if not filepath.exists():
        result["error"] = "Arquivo nao encontrado"
        result["fallback_triggered"] = True
        return result
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        result["error"] = f"JSON invalido: {e}"
        result["fallback_triggered"] = True
        return result
    except Exception as e:
        result["error"] = f"Erro ao ler: {e}"
        result["fallback_triggered"] = True
        return result
    
    # Valida chaves obrigatorias
    for key in schema.get("required_keys", []):
        if key not in data:
            result["missing_keys"].append(key)
    
    # Valida estrutura de comps (meta_db)
    if filename == "meta_db.json":
        comps = data.get("comps", {})
        if not isinstance(comps, dict):
            result["missing_keys"].append("comps (deve ser dict)")
        else:
            invalid_comps = []
            for comp_name, comp_data in comps.items():
                for req in schema.get("comp_required", []):
                    if req not in comp_data:
                        invalid_comps.append(f"{comp_name}.{req}")
            if invalid_comps:
                result["missing_keys"].extend(invalid_comps)
    
    result["valid"] = len(result["missing_keys"]) == 0
    if not result["valid"]:
        result["fallback_triggered"] = True
    
    return result


def repair_file(filename: str) -> bool:
    """Tenta reparar um arquivo JSON corrompido ou ausente"""
    repair_func = REPAIR_FUNCTIONS.get(filename)
    if not repair_func:
        logging.warning(f"Sem funcao de repair para {filename}")
        return False
    
    try:
        return repair_func()
    except Exception as e:
        logging.error(f"Falha ao reparar {filename}: {e}")
        return False


def validate_and_repair_all() -> Dict[str, Dict]:
    """Valida todos os JSONs e repara automaticamente os que falharem"""
    results = {}
    for filename in SCHEMAS:
        result = validate_json_file(filename)
        
        # Se invalido ou ausente, tenta reparar
        if not result["valid"]:
            repaired = repair_file(filename)
            result["repaired"] = repaired
            if repaired:
                # Re-valida apos repair
                result = validate_json_file(filename)
                result["repaired"] = True
                logging.info(f"Auto-repair bem-sucedido para {filename}")
        
        results[filename] = result
    return results


def validate_all() -> Dict[str, Dict]:
    """Valida todos os JSONs de data/ (sem auto-repair)"""
    results = {}
    for filename in SCHEMAS:
        results[filename] = validate_json_file(filename)
    return results


def get_validation_summary() -> str:
    """Retorna resumo legivel da validacao"""
    results = validate_and_repair_all()
    parts = []
    
    for filename, result in results.items():
        if result["valid"]:
            if result.get("repaired"):
                parts.append(f"  {filename}: REPARADO OK")
            else:
                parts.append(f"  {filename}: OK")
        elif result["fallback_triggered"]:
            parts.append(f"  {filename}: FALLBACK ({result.get('error', 'invalid')})")
        else:
            parts.append(f"  {filename}: INVALID ({', '.join(result['missing_keys'])})")
    
    return "\n".join(parts)


def validate_meta_comp(comp: dict) -> bool:
    """Valida uma composicao individual antes de usar"""
    if not isinstance(comp, dict):
        return False
    
    required = ["units", "tier"]
    return all(k in comp for k in required)


def validate_opponent_entry(entry: dict) -> bool:
    """Valida entrada de oponente"""
    if not isinstance(entry, dict):
        return False
    
    # Pelo menos precisa ter nome ou dados
    return len(entry) > 0


def validate_api_response(data: dict, expected_keys: List[str]) -> bool:
    """Valida resposta de API externa"""
    if not isinstance(data, dict):
        return False
    return all(k in data for k in expected_keys)
