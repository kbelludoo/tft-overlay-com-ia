import json, os, logging
from pathlib import Path
from .data import pt, pt_item, pt_augment, TFT17_TO_NAME, NAME_TO_TFT17, CHAMPION_PT, ITEM_PT, AUGMENT_PT

PROJECT_DIR = Path(__file__).parent.parent
META_JSON = PROJECT_DIR / "data" / "meta_db.json"

class MetaDB:
    def __init__(self, player_rank_tier="GOLD", player_rank_div="IV"):
        self.player_rank_tier = player_rank_tier
        self.player_rank_div = player_rank_div
        self.data = self._load_data()
    
    def update_rank(self, tier, div=""):
        """Atualiza rank do jogador e recarrega dados"""
        self.player_rank_tier = tier
        self.player_rank_div = div
        self.data = self._load_data()
    
    def _load_data(self):
        """Carrega meta de JSON externo ou usa hardcoded"""
        if META_JSON.exists():
            try:
                with open(META_JSON, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if "comps" in data:
                    return data
            except Exception as e:
                import logging
                logging.warning(f"Erro ao carregar meta JSON: {e}, usando hardcoded")
        return self._hardcoded_data()
    
    def _hardcoded_data(self):
        return {
            "comps": {
                "Dark Star Flex": {
                    "units": ["Jhin", "Kai'Sa", "Mordekaiser", "Chogath", "Karma", "Tahm Kench", "Galio", "Nunu", "Bard"],
                    "core_items": {"Jhin": ["InfinityEdge", "RapidFireCannon", "LastWhisper"], "Kai'Sa": ["Guinsoos", "Rabadon", "JeweledGauntlet"]},
                    "augments": ["TraitTree", "MayTheFoursBeWithYou", "HoldTheLine"],
                    "positioning": "Jhin/Kai'Sa atras, tanks na frente, Karma entre tanque e carry",
                    "tanks": ["Mordekaiser", "Cho'Gath", "Tahm Kench", "Galio", "Nunu"],
                    "levels": "Estratégia: Fast 8. Lvl 5: Morde+Cho+Karma+Jinx/Aatrox | Lvl 6: +Jhin+Kaisa | Lvl 7: +Tahm+Nunu | Lvl 8: +Galio (roll pra 2★) | Lvl 9: +Bard",
                    "dicas": "Faça econômia forte early com Dark Star (3). Coloque Jhin no canto oposto ao carry inimigo. NUNCA coloque Karma na frente. No late game, coloque Galio na linha de frente com itens de tank. Se conseguir 3 estrelas no Jhin ou Kaisa, é top 1 garantido.",
                    "tier": "S"
                },
                "Corki Riven": {
                    "units": ["Corki", "Riven", "Bard", "Bel'Veth", "Gwen", "Kai'Sa", "Poppy", "Nunu"],
                    "core_items": {"Corki": ["BlueBuff", "JeweledGauntlet", "Rabadon"], "Riven": ["InfinityEdge", "Bloodthirster", "LastWhisper"]},
                    "augments": ["BoxingLessons", "TraitTree"],
                    "positioning": "Corki no meio, Riven de flank, tanks na frente",
                    "tanks": ["Poppy", "Nunu", "Gwen"],
                    "levels": "Estratégia: Slow roll no lvl 6. Lvl 5: Poppy+Nunu+Corki+Riven | Lvl 6: +Gwen (role ate 2★) | Lvl 7: +BelVeth | Lvl 8: +Kaisa | Lvl 9: +Bard",
                    "dicas": "Role até 50 gold antes de subir nivel. Corki é o carry principal - protect ele com os tanks. Riven flanqueia pelo lado. Se pegar 3 estrelas no Corki, é gg. Evite colocar Corki no canto pois inimigos com Sniper vão focar ele.",
                    "tier": "S"
                },
                "Aurelion Sol Flex": {
                    "units": ["Aurelion Sol", "The Mighty Mech", "Viktor", "Kai'Sa", "Morgana", "Poppy", "Nunu", "Tahm Kench"],
                    "core_items": {"Aurelion Sol": ["BlueBuff", "Rabadon", "JeweledGauntlet"], "The Mighty Mech": ["Warmogs", "DragonClaw", "Gargoyle"]},
                    "augments": ["Lineup", "SpreadTheLove"],
                    "positioning": "Aurelion Sol no meio, Mech na frente, Viktor protegido",
                    "tanks": ["The Mighty Mech", "Poppy", "Nunu", "Tahm Kench"],
                    "levels": "Estratégia: Fast 8. Lvl 5: Poppy+Nunu+Morg+Asol | Lvl 6: +Mech | Lvl 7: +Viktor | Lvl 8: +Kaisa+Tahm (roll pra 2★ Asol/Mech) | Lvl 9: +Bard",
                    "dicas": "Priorize 2 estrelas no Aurelion Sol ASAP. Use The Mighty Mech como tank absoluto com 3 itens defensivos. Viktor é segundo carry - dê items AP leftovers. No early, use 2 Sorcerers + 2 Vanguards. No late game, adicione Bard para sinergia de utilidade.",
                    "tier": "S"
                },
                "Karma LB Duo": {
                    "units": ["Karma", "LeBlanc", "Kai'Sa", "Jhin", "Morgana", "Poppy", "Nunu", "Tahm Kench"],
                    "core_items": {"Karma": ["BlueBuff", "JeweledGauntlet", "Rabadon"], "LeBlanc": ["BlueBuff", "JeweledGauntlet", "Rabadon"], "Kai'Sa": ["Guinsoos", "InfinityEdge", "LastWhisper"]},
                    "augments": ["TwoTanky", "TraitTree"],
                    "positioning": "Karma/LeBlanc centro, tanks nas pontas",
                    "tanks": ["Poppy", "Nunu", "Tahm Kench"],
                    "levels": "Estratégia: Slow roll no lvl 6. Lvl 5: Poppy+Nunu+Karma+LeBlanc | Lvl 6: +Morgana (role 3★ Karma/LB) | Lvl 7: +Jhin | Lvl 8: +Kaisa | Lvl 9: +Tahm",
                    "dicas": "Karma e LeBlanc compartilham items AP - de os melhores para a que estiver mais perto de 3 estrelas. Kaisa é carry AD de backup. Early game fraco: perca streaks intencionalmente para pegar items prioritarios (Blue Buff). No late, posicione Karma e LeBlanc longe de assassinos.",
                    "tier": "A"
                },
                "Kaisa Karma": {
                    "units": ["Kai'Sa", "Karma", "Vex", "Jhin", "Morgana", "Poppy", "Nunu", "Tahm Kench"],
                    "core_items": {"Kai'Sa": ["Guinsoos", "Rabadon", "JeweledGauntlet"], "Karma": ["BlueBuff", "Rabadon", "JeweledGauntlet"]},
                    "augments": ["TraitTree", "MakeshiftArmor"],
                    "positioning": "Kai'Sa atras, Karma protegida, tanks na frente",
                    "tanks": ["Poppy", "Nunu", "Vex", "Tahm Kench"],
                    "levels": "Estratégia: Fast 8. Lvl 5: Poppy+Nunu+Karma+Morgana | Lvl 6: +Kaisa | Lvl 7: +Vex | Lvl 8: +Jhin (role 2★ Kaisa) | Lvl 9: +Tahm",
                    "dicas": "Kaisa é a carry principal - dê Guinsoos+Rabadon nela. Karma suporta com Blue Buff. Vex é um ótimo tank secundário. Early: use 2 Sorcerers + 2 Vanguards. No late game, posicione Kaisa no centro protegida por uma parede de tanks.",
                    "tier": "A"
                },
                "Samira Knockup": {
                    "units": ["Samira", "Kai'Sa", "Jhin", "Morgana", "Poppy", "Nunu", "Tahm Kench", "Vex"],
                    "core_items": {"Samira": ["InfinityEdge", "Bloodthirster", "LastWhisper"], "Kai'Sa": ["Guinsoos", "Rabadon"]},
                    "augments": ["TwoTanky", "TraitTree"],
                    "positioning": "Samira no meio protegido, flanqueadores nas laterais",
                    "tanks": ["Poppy", "Nunu", "Vex", "Tahm Kench"],
                    "levels": "Estratégia: Slow roll no lvl 6. Lvl 5: Poppy+Nunu+Samira+Morgana | Lvl 6: +Vex (role 3★ Samira) | Lvl 7: +Jhin | Lvl 8: +Kaisa | Lvl 9: +Tahm",
                    "dicas": "Samira precisa de 3 estrelas para carregar - foque em rolá-la. Bloodthirster é essencial para o sustain dela. Use os tanks para criar espaço. Early game fraco, então perca streaks intencionalmente. No late, Kaisa vira segundo carry com items AP.",
                    "tier": "B"
                },
                "Fast 9 Jhin Meeple": {
                    "units": ["Jhin", "Meepsie", "Mordekaiser", "Chogath", "Kai'Sa", "Karma", "Poppy", "Nunu", "Tahm Kench"],
                    "core_items": {"Jhin": ["InfinityEdge", "RapidFireCannon", "LastWhisper"], "Meepsie": ["Warmogs", "DragonClaw", "Gargoyle"]},
                    "augments": ["MayTheFoursBeWithYou"],
                    "positioning": "Jhin canto seguro, Meepsie tank principal",
                    "tanks": ["Meepsie", "Mordekaiser", "Cho'Gath", "Poppy", "Nunu", "Tahm Kench"],
                    "levels": "Estratégia: Fast 9 rush. Lvl 5: Morde+Cho+Jhin+Karma | Lvl 6: +Meepsie | Lvl 7: +Poppy+Nunu | Lvl 8: +Kaisa (NÃO role, compre XP) | Lvl 9: +Tahm+Bard (role tudo)",
                    "dicas": "Estratégia de rush level 9: compre xp todo turno ate level 8 antes de 4-2. Use uma compra inicial forte (2 Sniper + 2 Vanguard). Meepsie é o melhor tank - coloque os 3 items defensivos nele. Jhin no canto oposto ao carry inimigo. Venda unidades temporárias para financiar o rush.",
                    "tier": "A"
                },
                "Veigar Printer": {
                    "units": ["Veigar", "Kai'Sa", "Karma", "Vex", "Morgana", "Poppy", "Nunu", "Tahm Kench"],
                    "core_items": {"Veigar": ["BlueBuff", "Rabadon", "JeweledGauntlet"], "Kai'Sa": ["Guinsoos", "InfinityEdge"]},
                    "augments": ["MakeshiftArmor", "TraitTree"],
                    "positioning": "Veigar protegido no meio, tanks ao redor",
                    "tanks": ["Poppy", "Nunu", "Vex", "Tahm Kench"],
                    "levels": "Estratégia: Slow roll no lvl 7. Lvl 5: Poppy+Nunu+Morgana+Veigar | Lvl 6: +Karma | Lvl 7: +Vex (role 3★ Veigar) | Lvl 8: +Kaisa | Lvl 9: +Tahm",
                    "dicas": "Veigar escala com AP - Blue Buff + Rabadon são obrigatorios. Cada habilidade reduz o HP do inimigo e stacka o AP dele. Proteja Veigar com uma parede de tanks. Kaisa é carry AD de backup. No late, adicione mais Sorcerers para multiplicar o dano do Veigar.",
                    "tier": "B"
                },
                "Yordle Marawlers": {
                    "units": ["Master Yi", "Briar", "Poppy", "Nunu", "Tahm Kench", "Teemo"],
                    "core_items": {"Master Yi": ["InfinityEdge", "Bloodthirster", "LastWhisper"], "Briar": ["Warmogs", "DragonClaw"]},
                    "augments": ["TreatedS2", "TwoTanky"],
                    "positioning": "Yi flanqueando, tanks na frente",
                    "tanks": ["Briar", "Poppy", "Nunu", "Tahm Kench"],
                    "levels": "Estratégia: Slow roll no lvl 6. Lvl 5: Poppy+Nunu+Yi+Teemo | Lvl 6: +Briar (role 3★ Yi) | Lvl 7: +Tahm | Lvl 8-9: complete com Yordles",
                    "dicas": "Master Yi precisa de 3 estrelas - role pesado no level 6. Bloodthirster + Infinity Edge é core. Briar é o tank principal. Teemo serve como suporte e sinergia de trait. Early game forte com 3 Yordle. No late game, adicione mais Yordles para buffar o time todo.",
                    "tier": "A"
                }
            }
        }

    def _get_comps_for_rank(self):
        """Filtra composicoes do rank do jogador ou retorna todas se nao houver filtro"""
        tier = self.player_rank_tier
        div = self.player_rank_div
        
        # Se o JSON tem dados por rank, filtra
        comps = self.data.get("comps", {})
        rank_comps = {}
        
        for name, info in comps.items():
            rt = info.get("rank_tier", "")
            rd = info.get("rank_div", "")
            
            # Se nao tem rank_tier, e comp generica (hardcoded) - inclui sempre
            if not rt:
                rank_comps[name] = info
            # Se tem rank_tier e match com rank do jogador
            elif rt == tier and (not div or rd == div or rd == ""):
                rank_comps[name] = info
        
        # Se encontrou comps especificas do rank, enriquece com dados padrao
        if rank_comps:
            for name, info in rank_comps.items():
                if not info.get("core_items"):
                    info["core_items"] = self._default_items_for_comp(info)
                if not info.get("tanks"):
                    info["tanks"] = self._default_tanks_for_comp(info)
                if not info.get("augments"):
                    info["augments"] = self._default_augments_for_comp(info)
                if not info.get("levels"):
                    info["levels"] = "Suba de nivel naturalmente. Faca economy ate o stage 4-1."
                if not info.get("dicas"):
                    wr = info.get("win_rate", "?")
                    games = info.get("games", "?")
                    info["dicas"] = f"Comp forte em {tier} {div} ({wr}% WR em {games} jogos). Foque em itens de dano no carry e itens defensivos no tank."
                if not info.get("porque"):
                    units = info.get("units", [])
                    traits = info.get("traits", [])
                    carry = pt(units[0]) if units else "?"
                    tank = pt(units[2]) if len(units) > 2 else "?"
                    trait_str = ", ".join(traits[:3]) if traits else "desconhecidos"
                    info["porque"] = f"{carry} como carry principal com sinergia de {trait_str}. {tank} como frontline defensivo. Comp escalavel com boa performance em mid/late game."
                if not info.get("como"):
                    info["como"] = f"Early: monte a base com os champions baratos. Mid: foque nos itens do carry ({carry}). Late: complete a comp com os ultimos champions e posicione conforme orientacao."
            return rank_comps
        
        # Senao retorna todas (fallback)
        return comps
    
    def _default_items_for_comp(self, info: dict) -> dict:
        units = info.get("units", [])
        items = {}
        carry_ad = ["InfinityEdge", "LastWhisper", "GuinsoosRageblade"]
        carry_ap = ["BlueBuff", "JeweledGauntlet", "RabadonsDeathcap"]
        tank_pri = ["WarmogsArmor", "DragonsClaw", "GargoyleStoneplate"]
        tank_uti = ["LocketOfTheIronSolari", "FrozenHeart", "Redemption"]
        support  = ["ZekesHerald", "MikaelsBlessing", "Redemption"]

        for i, u in enumerate(units):
            display = pt(u)
            if i == 0:
                items[display] = carry_ad[:3]
            elif i == 1:
                items[display] = carry_ap[:3]
            elif i == 2:
                items[display] = tank_pri[:3]
            elif i == 3:
                items[display] = tank_uti[:3]
            elif i == 4:
                items[display] = tank_pri[:2]
            elif i == 5:
                items[display] = tank_uti[:2]
            else:
                items[display] = support[:2]
        return items
    
    def _default_tanks_for_comp(self, info: dict) -> list:
        """Gera tanks padrao baseado nas units da composicao"""
        units = info.get("units", [])
        # Ultimas 3-4 units sao tanks
        return [pt(u) for u in units[-4:]] if len(units) >= 4 else [pt(u) for u in units[-2:]]
    
    def _default_augments_for_comp(self, info: dict) -> list:
        """Gera augments padrao baseado no tipo de comp"""
        units = info.get("units", [])
        augments = []
        
        # Detecta tipo de comp baseado nas units
        unit_names = [pt(u).lower() for u in units]
        
        # AP carries
        ap_champs = ["karma", "leblanc", "veigar", "aurelion sol", "viktor", "morgana"]
        if any(c in " ".join(unit_names) for c in ap_champs):
            augments.extend(["TraitTree", "MakeshiftArmor"])
        
        # AD carries
        ad_champs = ["jhin", "kaisa", "samira", "ezreal", "riven", "fiora"]
        if any(c in " ".join(unit_names) for c in ad_champs):
            augments.extend(["MayTheFoursBeWithYou", "HoldTheLine"])
        
        # Tanks
        tank_champs = ["maokai", "nunu", "tahm kench", "poppy", "ornn", "rammus"]
        if any(c in " ".join(unit_names) for c in tank_champs):
            augments.extend(["TwoTanky", "BoxingLessons"])
        
        # Se nao detectou tipo, retorna genericos
        if not augments:
            augments = ["TraitTree", "Lineup"]
        
        return augments[:3]  # Max 3 augments
    
    def get_comp(self, name):
        return self.data["comps"].get(name, {})

    def _get_champion_item_lookup(self) -> dict:
        comps = self.data.get("comps", {})
        lookup = {}
        for name, info in comps.items():
            items = info.get("core_items", {})
            if not isinstance(items, dict): continue
            for champ, champ_items in items.items():
                if not isinstance(champ_items, list) or not champ_items: continue
                if champ not in lookup:
                    lookup[champ] = {"count": 0, "items": {}}
                lookup[champ]["count"] += 1
                for item in champ_items:
                    if not item: continue
                    lookup[champ]["items"][item] = lookup[champ]["items"].get(item, 0) + 1
        return lookup

    def _get_comp_items_for_champ(self, champ_name: str, is_tank: bool, lookup: dict) -> list:
        entry = lookup.get(champ_name)
        if entry and entry["items"]:
            sorted_items = sorted(entry["items"].items(), key=lambda x: -x[1])
            return [item for item, _ in sorted_items[:3]]
        if is_tank:
            return ["WarmogsArmor", "DragonsClaw", "GargoyleStoneplate"]
        return ["InfinityEdge", "LastWhisper", "GuinsoosRageblade"]

    def _enrich_core_items(self, core_items: dict, units: list, tanks: list) -> dict:
        if not core_items:
            core_items = {}
        lookup = self._get_champion_item_lookup()
        for u in units:
            display = pt(u) if callable(pt) else str(u)
            if display not in core_items or not core_items.get(display):
                is_tank = display in tanks or u in tanks
                core_items[display] = self._get_comp_items_for_champ(display, is_tank, lookup)
        return core_items

    def get_comp_info(self, name):
        info = self.get_comp(name)
        units = info.get("units", [])
        core_items = info.get("core_items", {}) or {}
        tanks = info.get("tanks", [])

        if not core_items:
            core_items = self._default_items_for_comp(info)

        core_items = self._enrich_core_items(core_items, units, tanks)

        return {
            "comp": name,
            "tier": info.get("tier", "B"),
            "units": units,
            "core_items": core_items,
            "augments": info.get("augments", []),
            "positioning": info.get("positioning", "Position units strategically"),
            "dicas": info.get("dicas", ""),
            "levels": info.get("levels", ""),
            "tanks": info.get("tanks", []),
            "win_rate": info.get("win_rate", ""),
            "avg_placement": info.get("avg_placement", ""),
            "games": info.get("games", ""),
            "counters": {}
        }

    def suggest_by_rank(self) -> dict:
        """Sugere melhor comp para o rank do jogador"""
        comps = self._get_comps_for_rank()
        if not comps:
            return {"name": "Sem dados para seu rank...", "match": 0, "tier": "N/A", "core_items": {}, "augments": [], "positioning": "Aguarde", "counters": {}}
        
        # Ordena por win_rate (se disponivel) ou tier
        def comp_score(item):
            name, info = item
            wr = info.get("win_rate", 0)
            tier_order = {"S": 3, "A": 2, "B": 1}
            return (wr, tier_order.get(info.get("tier", "B"), 0))
        
        best = max(comps.items(), key=comp_score)
        return self.get_comp_info(best[0])

    def suggest_by_opponent(self, opponents_data: list) -> dict:
        if not opponents_data:
            return self.suggest_by_rank()
        
        comps = self._get_comps_for_rank()
        if not comps:
            return {"name": "Sem dados...", "match": 0, "tier": "N/A", "core_items": {}, "augments": [], "positioning": "Aguarde", "counters": {}}
        
        comp_scores = {name: 0 for name in comps}
        
        for opp in opponents_data:
            traits = opp.get("traits", [])
            comps_opps = opp.get("recent_comps", [])
            
            for comp_name, info in comps.items():
                if any(t in traits for t in ["Sniper", "Darkspell", "Vanguard"]):
                    if "Dark Star" in comp_name or "Kai'Sa" in str(info.get("units", [])):
                        comp_scores[comp_name] += 2
                if any(c in comps_opps for c in ["Karma", "LB", "Kaisa"]):
                    if comp_name in ["Karma LB Duo", "Kaisa Karma"]:
                        comp_scores[comp_name] += 3
        
        best_comp = max(comp_scores, key=comp_scores.get)
        if comp_scores[best_comp] > 0:
            return self.get_comp_info(best_comp)
        
        return self.suggest_by_rank()

    def suggest_by_board(self, my_board: list, stage: str) -> dict:
        if not my_board:
            return {"name": "Aguardando board...", "match": 0, "tier": "N/A", "core_items": {}, "augments": [], "positioning": "Aguarde unidades na loja", "counters": {}}
        
        comps = self._get_comps_for_rank()
        best, max_match = None, 0
        for comp_name, info in comps.items():
            match = len(set(my_board) & set(info.get("units", [])))
            if match > max_match:
                max_match, best = match, comp_name
        
        if max_match >= 2 and best:
            return {"name": best, "match": max_match, **self.get_comp_info(best)}
        
        return self.suggest_by_rank()

    def all_comps(self):
        comps = self._get_comps_for_rank()
        return [(name, info.get("tier", "B")) for name, info in comps.items()]

    def get_top_comps(self, tier="S"):
        if tier == "S":
            tier = ["S", "A"]
        elif tier == "A":
            tier = ["A", "B"]
        else:
            tier = [tier]

        comps = self._get_comps_for_rank()
        result = []
        for name, info in comps.items():
            if info.get("tier", "B") in tier:
                core_items = info.get("core_items", {})
                if not core_items:
                    core_items = self._default_items_for_comp(info)
                info["core_items"] = self._enrich_core_items(core_items, info.get("units", []), info.get("tanks", []))
                result.append({"name": name, **info})
        return result