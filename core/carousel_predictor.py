"""
Preditor de Carousel - Decisões no Carousel.

Trigger no estágio X-2 (durante combate). Pré-calcula e cacheia para exibir
instantaneamente quando a fase do carousel começar.

Análise:
- Gaps no board (unidades faltantes)
- Itens faltantes da comp
- Oponentes que podem pegar o mesmo item
- Priorização de items por stage
"""
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class CarouselPriority(Enum):
    """Prioridade de item no carousel."""
    CRITICAL = "critical"  # Necessário para comp
    HIGH = "high"          # Muito útil
    MEDIUM = "medium"      # Útil
    LOW = "low"           # Pode esperar


@dataclass
class CarouselSuggestion:
    """Sugestão para o carousel."""
    item: str
    holder: str  # Quem deve pegar
    reason: str
    priority: CarouselPriority
    contested: bool  # Se oponente pode pegar
    alternative: Optional[str]  # Alternativa se disputando


@dataclass
class CarouselPrediction:
    """Predição completa do carousel."""
    stage: str
    suggestions: List[CarouselSuggestion]
    board_gaps: List[str]  # Units que faltam na comp
    items_missing: List[str]  # Itens que faltam
    overall_strategy: str


# Mapeamento de comps -> itens prioritários
COMP_PRIORITY_ITEMS = {
    "Dark Star Flex": {
        "Jhin": ["InfinityEdge", "RapidFireCannon", "LastWhisper"],
        "Kai'Sa": ["Guinsoos", "Rabadon", "JeweledGauntlet"]
    },
    "Corki Riven": {
        "Corki": ["BlueBuff", "JeweledGauntlet", "Rabadon"],
        "Riven": ["InfinityEdge", "Bloodthirster", "LastWhisper"]
    },
    "Aurelion Sol Flex": {
        "Aurelion Sol": ["BlueBuff", "Rabadon", "JeweledGauntlet"],
        "The Mighty Mech": ["WarmogsArmor", "DragonClaw", "GargoyleStoneplate"]
    },
    "Karma LB Duo": {
        "Karma": ["BlueBuff", "JeweledGauntlet", "Rabadon"],
        "LeBlanc": ["BlueBuff", "JeweledGauntlet", "Rabadon"]
    },
    "Kaisa Karma": {
        "Kai'Sa": ["Guinsoos", "Rabadon", "JeweledGauntlet"],
        "Karma": ["BlueBuff", "Rabadon", "JeweledGauntlet"]
    },
    "Samira Knockup": {
        "Samira": ["InfinityEdge", "Bloodthirster", "LastWhisper"]
    },
    "Fast 9 Jhin Meeple": {
        "Jhin": ["InfinityEdge", "RapidFireCannon", "LastWhisper"],
        "Meepsie": ["WarmogsArmor", "DragonClaw", "GargoyleStoneplate"]
    },
    "Veigar Printer": {
        "Veigar": ["BlueBuff", "Rabadon", "JeweledGauntlet"]
    },
    "Yordle Marawlers": {
        "Master Yi": ["InfinityEdge", "Bloodthirster", "LastWhisper"],
        "Briar": ["WarmogsArmor", "DragonClaw"]
    }
}

# Items universais importantes
UNIVERSAL_PRIORITY = {
    "BlueBuff": "CRITICAL",      # Mana para carries
    "WarmogsArmor": "HIGH",      # Tank sustain
    "InfinityEdge": "HIGH",       # Carry AD
    "JeweledGauntlet": "HIGH",    # Carry AP
    "RabadonsDeathcap": "MEDIUM", # Scaling AP
    "GuinsoosRageblade": "MEDIUM", # Kai'Sa/AS carries
    "GargoyleStoneplate": "HIGH", # Tank defensive
    "Bloodthirster": "MEDIUM",    # AD sustain
}


class CarouselPredictor:
    """
    Preditor de decisões no Carousel.
    Pré-calcula durante combate para exibir instantaneamente no carousel.
    """

    def __init__(self):
        self._cached_prediction: Optional[CarouselPrediction] = None
        self._last_stage: str = ""
        self._trigger_stages = {"2-5", "3-5", "4-5", "5-5", "6-5", "7-5"}  # Carousels

    def should_predict(self, current_stage: str, next_phase: str) -> bool:
        """Determina se deve fazer predição."""
        # Trigger: durante combate antes do carousel
        current_stage_num = current_stage.split("-")[0] if current_stage else "0"
        next_carousel_stage = f"{current_stage_num}-5"

        # Se está em estágio ímpar e próximo é carousel
        if next_phase == "WaitingForCarousel":
            return True

        # Pré-calcula no estágio anterior (2-4, 3-4, etc)
        stage_parts = current_stage.split("-")
        if len(stage_parts) == 2:
            stage_num, round_num = stage_parts
            if int(round_num) >= 4:  # Durante combate
                return True

        return False

    def predict(self, current_stage: str, current_comp: str,
                current_items: List[str], board_units: List[str],
                missing_units: List[str], opponent_items: Dict[str, List[str]] = None) -> CarouselPrediction:
        """
        Gera predição de carousel.

        Args:
            current_stage: Stage atual
            current_comp: Composição atual
            current_items: Itens que o jogador já tem
            board_units: Units no board
            missing_units: Units que faltam na comp
            opponent_items: Itens que oponentes têm (para detectar contention)

        Returns:
            CarouselPrediction com sugestões
        """
        opponent_items = opponent_items or {}

        suggestions = []
        items_missing = []
        board_gaps = missing_units

        # 1. Verificar prioridade da comp
        comp_priority = COMP_PRIORITY_ITEMS.get(current_comp, {})

        # 2. Para cada carry, verificar itens faltantes
        for carry, needed_items in comp_priority.items():
            for item in needed_items:
                if item not in current_items:
                    items_missing.append(item)

                    # Verificar contention (oponente pode pegar?)
                    contested = self._is_contested(item, opponent_items, current_items)

                    # Definir prioridade
                    priority = self._get_priority(item, current_comp, needed_items)

                    # Encontrar holder (quem precisa do item)
                    holder = self._find_holder(item, comp_priority)

                    suggestions.append(CarouselSuggestion(
                        item=item,
                        holder=holder,
                        reason=self._get_reason(item, priority),
                        priority=priority,
                        contested=contested,
                        alternative=self._get_alternative(item, priority, current_items)
                    ))

        # 3. Se não tem comp específica, usar universais
        if not suggestions:
            for item, priority_str in UNIVERSAL_PRIORITY.items():
                if item not in current_items:
                    priority = CarouselPriority(priority_str.lower())
                    if priority in [CarouselPriority.CRITICAL, CarouselPriority.HIGH]:
                        contested = self._is_contested(item, opponent_items, current_items)
                        suggestions.append(CarouselSuggestion(
                            item=item,
                            holder="Carry Principal",
                            reason=f"Item universal - {priority_str}",
                            priority=priority,
                            contested=contested,
                            alternative=None
                        ))

        # 4. Ordenar por prioridade
        suggestions.sort(key=lambda x: {
            CarouselPriority.CRITICAL: 0,
            CarouselPriority.HIGH: 1,
            CarouselPriority.MEDIUM: 2,
            CarouselPriority.LOW: 3
        }[x.priority])

        # 5. Cachear predição
        self._cached_prediction = CarouselPrediction(
            stage=current_stage,
            suggestions=suggestions,
            board_gaps=board_gaps,
            items_missing=items_missing,
            overall_strategy=self._build_strategy(suggestions)
        )

        self._last_stage = current_stage
        logger.info(f"Carousel prediction cached: {len(suggestions)} suggestions")

        return self._cached_prediction

    def _is_contested(self, item: str, opponent_items: Dict[str, List[str]],
                     my_items: List[str]) -> bool:
        """Verifica se item está sendo contentionado por oponentes."""
        if not opponent_items:
            return False

        # Se eu já tenho o item, não é contested
        if item in my_items:
            return False

        # Verificar se oponente tem ou precisa deste item
        for opp_items in opponent_items.values():
            if item in opp_items:
                return True

        # Heurística: oponentes da mesma comp = contention
        return False

    def _get_priority(self, item: str, comp: str, needed_items: List[str]) -> CarouselPriority:
        """Determina prioridade do item."""
        # Críticos: BlueBuff, primeira versão de itens de carry
        if item == "BlueBuff":
            return CarouselPriority.CRITICAL

        # Primeiro item de carry = HIGH
        if item == needed_items[0]:
            return CarouselPriority.HIGH

        # Segundo item = MEDIUM
        if len(needed_items) > 1 and item == needed_items[1]:
            return CarouselPriority.MEDIUM

        return CarouselPriority.LOW

    def _find_holder(self, item: str, comp_priority: Dict) -> str:
        """Encontra quem deve pegar o item."""
        # Map item type to holder
        ap_items = {"BlueBuff", "JeweledGauntlet", "RabadonsDeathcap", "ArchangelsStaff"}
        ad_items = {"InfinityEdge", "RapidFireCannon", "LastWhisper", "Bloodthirster"}
        tank_items = {"WarmogsArmor", "DragonClaw", "GargoyleStoneplate"}

        if item in ap_items:
            return comp_priority.get("Karma") or comp_priority.get("Kai'Sa") or "AP Carry"
        elif item in ad_items:
            return comp_priority.get("Jhin") or comp_priority.get("Samira") or "AD Carry"
        elif item in tank_items:
            return "Tank Principal"

        return "Unused"

    def _get_reason(self, item: str, priority: CarouselPriority) -> str:
        """Gera reason para o item."""
        reasons = {
            CarouselPriority.CRITICAL: "Essencial para funcionamento da comp",
            CarouselPriority.HIGH: "Primeiro item do carry - grande impacto",
            CarouselPriority.MEDIUM: "Item útil mas não urgente",
            CarouselPriority.LOW: "Pode pegar depois"
        }
        return reasons.get(priority, "")

    def _get_alternative(self, item: str, priority: CarouselPriority,
                        current_items: List[str]) -> Optional[str]:
        """Retorna alternativa se item estiver contested."""
        alternatives = {
            "BlueBuff": "ArchangelsStaff",
            "InfinityEdge": "Bloodthirster",
            "WarmogsArmor": "GargoyleStoneplate",
            "JeweledGauntlet": "RabadonsDeathcap",
            "GuinsoosRageblade": "InfinityEdge"
        }

        alt = alternatives.get(item)
        if alt and alt not in current_items:
            return alt

        return None

    def _build_strategy(self, suggestions: List[CarouselSuggestion]) -> str:
        """Constrói estratégia geral."""
        if not suggestions:
            return "Nenhum item crítico faltando - pegar item flexível"

        critical = [s for s in suggestions if s.priority == CarouselPriority.CRITICAL]
        high = [s for s in suggestions if s.priority == CarouselPriority.HIGH]

        if critical:
            return f"PEGUE {critical[0].item} - {critical[0].reason}"
        elif high:
            return f"Considere {high[0].item} -_PRIORITY para {high[0].holder}"

        return "Pegar item que funcione para backup carry"

    def get_cached(self) -> Optional[CarouselPrediction]:
        """Retorna predição cacheada."""
        return self._cached_prediction

    def clear_cache(self):
        """Limpa cache (novo jogo)."""
        self._cached_prediction = None
        logger.info("Carousel prediction cache cleared")


def format_carousel_display(prediction: CarouselPrediction, opacity: float = 1.0) -> Dict:
    """Formata predição para display na HUD."""
    return {
        "opacity": opacity,
        "stage": prediction.stage,
        "strategy": prediction.overall_strategy,
        "suggestions": [
            {
                "icon": "🔴" if s.priority == CarouselPriority.CRITICAL else
                       "🟡" if s.priority == CarouselPriority.HIGH else "🟢",
                "item": s.item,
                "holder": s.holder,
                "contested": "⚠️" if s.contested else "",
                "alt": f"→ {s.alternative}" if s.alternative else ""
            }
            for s in prediction.suggestions[:3]  # Top 3
        ]
    }


# Instância global
carousel_predictor = CarouselPredictor()


def create_carousel_predictor() -> CarouselPredictor:
    """Factory para criar predictor."""
    return CarouselPredictor()


def predict_carousel(stage: str, comp: str, items: List[str],
                   board: List[str], missing: List[str],
                   opponent_items: Dict = None) -> Dict:
    """
    Função de conveniência para predição.
    Retorna dict formatado para display na HUD.
    """
    prediction = carousel_predictor.predict(
        stage, comp, items, board, missing, opponent_items
    )

    # Durante combate: opacity 0.6, no carousel: opacity 1.0
    in_carousel = "5" in stage or "Carousel" in stage
    opacity = 1.0 if in_carousel else 0.6

    return format_carousel_display(prediction, opacity)