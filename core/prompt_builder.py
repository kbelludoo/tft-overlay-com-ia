import json, logging
from .lcu_parser import GameState
from .memory_db import MemoryDB
from .meta_db import MetaDB, pt, pt_item, pt_augment
from .data import normalize_augment
from .prompt_compressor import compress_history, compress_opponents
from .feedback_calibrator import feedback_calibrator

class PromptBuilder:
    def __init__(self, mem: MemoryDB, meta: MetaDB):
        self.mem, self.meta = mem, meta

    def build(self, state: GameState, opponent_analysis: dict = None, my_rank: dict = None, registered_augments: list = None) -> str:
        ctx = self.mem.get_context()
        pattern = self.mem.get_cached_pattern(state.stage, [t for o in state.opponents for t in o.get("traits",[])])
        rank_text = f"Seu rank: {my_rank.get('tier', 'Unknown')} {my_rank.get('rank', '')} ({my_rank.get('lp', 0)} LP)\n" if my_rank else ""
        pattern_text = f"Ja venceu {pattern['trials']}x com {pattern['comp']} neste cenario ({pattern['success']*100:.0f}% winrate)" if pattern else "Sem padrao consolidado ainda"
        recent = self.mem.get_recent_matches(5)
        recent_text = compress_history(recent)

        chosen_meta = self.meta.suggest_by_board(state.my_board, state.stage)

        opponent_text = ""
        if opponent_analysis:
            opp_summary = compress_opponents(opponent_analysis)
            opponent_text = f"\n[OPONENTES - ANALISE DETALHADA]\n{opp_summary}\n"
            
            opp_comps = set()
            for name, data in opponent_analysis.items():
                for comp_name, count in data.get("recent_comps", []):
                    opp_comps.add(comp_name)
            
            if opp_comps:
                counter_list = []
                all_comps = self.meta.get_top_comps("S")
                for c in all_comps:
                    c_name = c.get("name", "")
                    counters = []
                    for opp_comp in opp_comps:
                        if opp_comp.lower() in c.get("counters", {}).keys():
                            counters.append(opp_comp)
                    if counters:
                        counter_list.append(f"- {c_name} counters: {', '.join(counters)}")
                
                if counter_list:
                    opponent_text += "\n[COUNTER SUGGESTIONS]\n" + "\n".join(counter_list[:5]) + "\n"
            
            opp_avg = [data.get("avg_placement", 8) for data in opponent_analysis.values()]
            avg_placement = sum(opp_avg) / len(opp_avg) if opp_avg else 8
            meta_wr = float(chosen_meta.get("win_rate", 50) or 50)
            opp_penalty = max(0, (avg_placement - 4.5) * 8)
            win_est = max(20, min(90, int(meta_wr - opp_penalty)))
            opponent_text += f"\nWin rate estimado da comp: {meta_wr}% (meta). Ajuste vs oponentes: ~{win_est}% (media colocacao oponentes: {avg_placement:.1f})\n"

        augments_str = ", ".join([pt_augment(a) for a in state.my_augments]) if state.my_augments else "Nenhum selecionado"

        # ── Augments registrados: filtra comps da meta ──────────────────────────
        augment_match_str = ""
        comp_list_str = ""

        if registered_augments:
            reg_internal = [normalize_augment(a) for a in registered_augments if a]
            reg_pt = [pt_augment(a) for a in reg_internal]

            all_comps = self.meta.get_top_comps("S")
            scored = []
            for c in all_comps:
                comp_augs = c.get("augments", [])
                match_count = sum(1 for a in reg_internal if a in comp_augs)
                if match_count > 0:
                    scored.append((match_count, c))

            # Ordena por mais matches, depois por tier
            tier_order = {"S": 3, "A": 2, "B": 1}
            scored.sort(key=lambda x: (x[0], tier_order.get(x[1].get("tier", "B"), 0)), reverse=True)

            if scored:
                # Usa a melhor comp com augment match como sugestao principal
                chosen_meta = scored[0][1]
                # Lista todas as comps que combinam
                comp_lines = []
                for _, c in scored[:5]:
                    c_augs = ", ".join(pt_augment(a) for a in c.get("augments", []))
                    comp_lines.append(f"- {c['name']} (Tier {c['tier']}) — augments: {c_augs}")
                comp_list_str = "\n".join(comp_lines)
                augment_match_str = (
                    f"⚠️ AUGMENTS JA ESCOLHIDOS: {', '.join(reg_pt)}\n"
                    "VOCE DEVE ESCOLHER UMA COMP DESTA LISTA:\n"
                    f"{comp_list_str}\n"
                )

        # ── Dados da comp escolhida ──────────────────────────────────────────────
        minha_comp = chosen_meta.get("name", "")
        minha_wr = ""
        for c in ctx.get("top_comps", []):
            if c["comp"] == minha_comp:
                minha_wr = f" (sua winrate: {c['w']}% em {c['t']} jogos)"
                break

        items_pt = {}
        for champ, items in chosen_meta.get('core_items', {}).items():
            champ_pt = pt(champ)
            items_pt[champ_pt] = [pt_item(i) for i in items]

        augments_pt = [pt_augment(a) for a in chosen_meta.get('augments', [])]
        tanks_pt = [pt(t) for t in chosen_meta.get('tanks', [])]

        prompt = (
            f"{rank_text}"
            f"{augment_match_str}"
            "Voce e um coach Grandmaster de TFT Set 17. "
            "Analise o estado atual do jogo e os oponentes para sugerir a MELHOR composicao.\n"
            "Retorne APENAS JSON valido em portugues, sem markdown:\n"
            '{"comp":"nome da comp","itens":"campeao: item1, item2, item3 | ...","augments":"aug1, aug2, aug3","posicionamento":"descricao do posicionamento","contra":"contra quem e forte","motivo":"por que essa comp","porque":"explicacao detalhada de por que jogar com essa comp (sinergias, vantagens, meta)","como":"guia completo de como jogar (economia, nivelamento, early/mid/late game, quando rollar)","viabilidade":85}\n'
            "viabilidade: 0-100 indicando quao forte e esta sugestao.\n"
            "\n[COMP SUGERIDA PELO META]\n"
            f"Comp: {chosen_meta['name']} (Tier {chosen_meta['tier']}){minha_wr}\n"
            f"Itens: {json.dumps(items_pt, ensure_ascii=False)}\n"
            f"Augments: {', '.join(augments_pt)}\n"
            f"Tanks: {', '.join(tanks_pt)}\n"
            f"Posicionamento: {chosen_meta.get('positioning','')}\n"
            "\n[SEU HISTORICO]\n"
            f"Win rate: {ctx['win_rate']}% | Segue dicas: {ctx['follow_rate']}% | Avaliacao: {ctx['avg_rating']}/5\n"
            f"Comps que funcionam: {', '.join(c['comp'] for c in ctx['top_comps']) if ctx['top_comps'] else 'Nenhuma'}\n"
            f"Evitar: {', '.join(ctx['avoid_comps']) if ctx['avoid_comps'] else 'Nenhuma'}\n"
            f"Resumo: {recent_text}\n"
            "\n[CALIBRACAO LOCAL]\n"
            f"{feedback_calibrator.inject_calibration(chosen_meta.get('name', ''))}\n"
            "\n[PADRAO LOCAL]\n"
            f"{pattern_text}\n"
            f"{opponent_text}"
            "\n[ESTADO ATUAL]\n"
            f"Stage: {state.stage} | Ouro: {state.gold} | Nivel: {state.level}\n"
            f"Augments atuais: {augments_str}\n"
            f"Board: {state.my_board[:5]} | Shop: {state.shop}\n"
            f"Oponentes: {[o['name'] for o in state.opponents]}\n"
            "\nINSTRUCOES:\n"
            "1. REGRA ABSOLUTA: escolha uma comp da lista acima que SINERGIZE com os augments ja escolhidos\n"
            "2. Sugira uma comp que COUNTER os oponentes atuais\n"
            "3. Indique os itens ideais para cada campeao\n"
            "4. Explique o posicionamento ideal\n"
            "5. Retorne APENAS o JSON em portugues"
        )
        return prompt
