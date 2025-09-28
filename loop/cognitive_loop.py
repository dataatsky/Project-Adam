import json
import time
import os
from typing import Optional, Callable
import copy
import logging

import config

from text_world import TextWorld
from loop.insight_engine import InsightEngine


class CognitiveLoop:
    def __init__(self, log_filename, log_headers, ui=None, experiment_tag="baseline", agent_id="adam1", memory=None, psyche=None, world_factory: Optional[Callable[[], TextWorld]] = None):
        self.log = logging.getLogger(__name__ + ".CognitiveLoop")
        # Initialize from config.AGENT_STATUS (deep-copied to avoid shared mutations)
        self.agent_status = copy.deepcopy(getattr(config, "AGENT_STATUS", {
            "emotional_state": {"mood": "neutral", "level": 0.1},
            "personality": {"curiosity": 0.8, "bravery": 0.6, "caution": 0.7},
            "needs": {"hunger": 0.1},
            "goal": "Find the source of the strange noises in the house.",
        }))
        self.memory = memory
        try:
            self.memory_id_counter = (self.memory.get_total_count() if self.memory else 0)
        except Exception:
            self.memory_id_counter = 0
        self.psyche = psyche
        self.is_running = True
        self.paused = False
        self._step_flag = False
        self.last_resonant_memories = []
        self.recent_memories = []
        self.log_filename = log_filename
        self.log_headers = log_headers
        self.current_world_state = {}
        self.current_mood = self.agent_status.get("emotional_state", {}).get("mood", "neutral")
        self.mood_intensity = float(self.agent_status.get("emotional_state", {}).get("level", 0.1))
        self.ui = ui
        self.insight = InsightEngine(history_len=24)
        self.experiment_tag = experiment_tag
        self.agent_id = agent_id
        self.cycle_counter = 0
        self.last_hypothetical = []
        self.world_factory = world_factory or TextWorld
        self.imagine_top_k = int(getattr(config, "IMAGINE_TOP_K", 3))
        try:
            self.cycle_sleep = float(getattr(config, "CYCLE_SLEEP", 5.0))
        except Exception:
            self.cycle_sleep = 5.0
        self.security = None
        self.recent_success_actions: list[tuple[str | None, str | None]] = []

    def attach_security(self, security):
        self.security = security
        if hasattr(self.security, "context"):
            self.security.context.loop = self

    def log_cycle_data(self, cycle_data):
        import csv
        try:
            with open(self.log_filename, mode="a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.log_headers)
                if f.tell() == 0:
                    writer.writeheader()
                writer.writerow(cycle_data)
        except Exception as e:
            print(f"CSV write error: {e}")

    # helpers to touch UI
    def _ui_status(self, txt):
        if self.ui:
            self.ui.set_status(txt)

    def _ui_vitals(self):
        if self.ui:
            self.ui.update_vitals(
                self.agent_status['emotional_state']['mood'],
                self.agent_status['emotional_state']['level'],
                self.agent_status['needs']['hunger']
            )

    def _ui_log(self, text):
        if self.ui:
            self.ui.append_log(text)

    # Controls
    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def step_once(self):
        self._step_flag = True

    def set_cycle_sleep(self, sec: float):
        try:
            self.cycle_sleep = max(0.1, float(sec))
        except Exception:
            pass

    # OODA steps
    def observe(self, world_state):
        self._ui_status("Observing…")
        self.log.info("— 1. OBSERVING —")
        self.log.debug(json.dumps(world_state, indent=2))
        self.current_world_state = world_state
        self._ui_vitals()
        return world_state

    def orient(self, world_state):
        self._ui_status("Orienting (Subconscious)…")
        self.log.info("— 2. ORIENTING —")
        sensory = world_state.get("sensory_events", [])
        query_text = " ".join([f"{e.get('type','')} of {e.get('object','')} which is {e.get('details','')}" for e in sensory if 'object' in e])
        if not query_text:
            print("No object-based sensory events for memory query.")
            self.last_resonant_memories = []
        else:
            self.last_resonant_memories = []
            try:
                if self.memory:
                    self.last_resonant_memories = self.memory.query_similar_texts(query_text, top_k=3)
                    self.log.debug(f"Resonant memories: {self.last_resonant_memories}")
            except Exception:
                self.last_resonant_memories = []
        payload = {
            "current_state": self.agent_status,
            "world_state": world_state,
            "resonant_memories": self.last_resonant_memories,
        }
        if self.security:
            payload = self.security.before_psyche("generate_impulse", payload)
        impulses = None
        if self.psyche:
            impulses = self.psyche.generate_impulse(payload)
        if self.security:
            impulses = impulses or {}
            self.security.after_psyche("generate_impulse", payload, impulses)
        if impulses:
            impulses = self._dampen_repeated_impulses(impulses)
            self.ui and self.ui.set_subconscious(
                impulses.get("emotional_shift", {}),
                impulses.get("impulses", []),
                self.last_resonant_memories,
            )
        return impulses

    def imagine_and_reflect(self, initial_impulses, world: TextWorld):
        self._ui_status("Imagining & Reflecting…")
        self.log.info("— 2.5. IMAGINE & REFLECT —")
        hypothetical = []
        top = sorted(initial_impulses.get("impulses", []), key=lambda x: x.get("urgency", 0), reverse=True)[: self.imagine_top_k]
        for imp in top:
            if not isinstance(imp, dict):
                continue
            action = {"verb": imp.get("verb"), "target": imp.get("target")}
            imagined = self.psyche.imagine(action) if self.psyche else "My imagination is fuzzy."
            sim = world.clone().process_action(action)
            hypothetical.append({
                "action": action,
                "imagined": imagined,
                "simulated": sim.get("reason"),
            })
        self.last_hypothetical = hypothetical
        self.ui and self.ui.set_imagination(hypothetical)
        payload = {
            "current_state": self.agent_status,
            "hypothetical_outcomes": hypothetical,
            "recent_memories": self.recent_memories,
        }
        reflection = {"final_action": {"verb": "wait", "target": "null"}, "reasoning": "Mind is blank."}
        if self.psyche:
            if self.security:
                payload = self.security.before_psyche("reflect", payload)
            reflection = self.psyche.reflect(payload)
            self.log.debug(f"Reflection: {reflection.get('reasoning')}")
        if self.security:
            self.security.after_psyche("reflect", payload, reflection)
        return reflection

    def decide(self, final_action, reasoning):
        self._ui_status("Deciding…")
        self.log.info("— 3. DECIDING —")
        self.log.debug(f"Chosen: {final_action}")
        self.ui and self.ui.set_decision(final_action, reasoning)
        return final_action, reasoning

    def act(self, world, action, reasoning, world_state, impulses):
        self._ui_status("Acting…")
        self.log.info("— 4. ACTING —")
        result = world.process_action(action)
        self.log.debug(f"Result: {result}")
        if result.get("state_change") and "hunger" in result["state_change"]:
            self.agent_status['needs']['hunger'] = max(0, self.agent_status['needs']['hunger'] + result['state_change']['hunger'])
        # Narrative memory
        sensed_objs = [e['object'] for e in world_state.get('sensory_events', []) if 'object' in e]
        sensed_str = f"I sensed {', '.join(sensed_objs)}." if sensed_objs else "I sensed nothing unusual."
        decision_str = f"I decided to {action['verb']}" if action.get('target') == 'null' else f"I decided to {action['verb']} the {action['target']}"
        reason = result.get('reason', 'it just happened.')
        event_desc = (
            f"I was in the {world.agent_location}. {sensed_str} My emotional state became {self.current_mood}. "
            f"{decision_str}. {'The result was: ' if result.get('success') else 'But it failed because '}" + reason
        )
        self.recent_memories.append(event_desc)
        if len(self.recent_memories) > 5:
            self.recent_memories.pop(0)
        # Store vector memory
        try:
            if self.memory:
                self.memory.upsert_texts([event_desc])
                self.memory_id_counter += 1
        except Exception as e:
            self.log.warning(f"Memory upsert error: {e}")
        # --- Insights & snapshot ---
        triggers = [f"{e.get('object')} : {e.get('details')}" for e in world_state.get('sensory_events', []) if 'object' in e]
        imps = impulses.get('impulses', []) if impulses else []
        emotional_delta = (impulses or {}).get('emotional_shift', {})
        self.insight.add_cycle(action=action, success=bool(result.get('success')), impulses=imps, triggers=triggers, mood=self.agent_status['emotional_state']['mood'])
        kpis = self.insight.compute_kpis()
        imagined_texts = []
        for hypo in self.last_hypothetical or []:
            try:
                act = hypo.get('action', {}) or {}
                verb = act.get('verb') or 'wait'
                target = act.get('target') or 'null'
                imagined_texts.append(f"{verb} {target}: {hypo.get('imagined', '')}")
            except Exception:
                continue
        imagined_join = "; ".join(filter(None, imagined_texts))
        causal = self.insight.causal_line(triggers=triggers, impulses=imps, action=action, imagined=imagined_join, simulated=result.get('reason', ''), emotional_delta=emotional_delta)
        cards = self.insight.cards(triggers=triggers, kpis=kpis, chosen=action, imagined=imagined_join, simulated=result.get('reason', ''), emotional_delta=emotional_delta)
        badges = self.insight.badges(kpis)
        threads = self.insight.threads()
        # Push to UI
        self.ui and self.ui.set_insights(badges=badges, cards=cards, causal_line=causal, threads=threads)
        # Log CSV with extended fields
        goal_state = world_state.get('goal') if isinstance(world_state, dict) else None
        goal_step = world_state.get('goal_step') if isinstance(world_state, dict) else None
        cycle_data = {
            "timestamp": time.time(),
            "cycle_num": self.cycle_counter,
            "experiment_tag": self.experiment_tag,
            "agent_id": self.agent_id,
            "world_time": world.world_time,
            "location": world.agent_location,
            "mood": self.current_mood,
            "mood_intensity": self.mood_intensity,
            "sensory_events": json.dumps(world_state.get('sensory_events', []), ensure_ascii=False),
            "resonant_memories": json.dumps(self.last_resonant_memories, ensure_ascii=False),
            "impulses": json.dumps(imps, ensure_ascii=False),
            "chosen_action": f"{action.get('verb')}_{action.get('target')}",
            "action_result": json.dumps(result, ensure_ascii=False),
            "imagined_outcomes": json.dumps([h.get("imagined", "") for h in self.last_hypothetical], ensure_ascii=False),
            "simulated_outcomes": json.dumps([h.get("simulated", "") for h in self.last_hypothetical], ensure_ascii=False),
            "emotional_delta": json.dumps(emotional_delta, ensure_ascii=False),
            "kpis": json.dumps(kpis, ensure_ascii=False),
            "snapshot": json.dumps({
                "triggers": triggers,
                "top_impulses": sorted(imps, key=lambda x: x.get('urgency', 0), reverse=True)[:3],
                "chosen": action,
                "simulated": result.get('reason', ''),
                "emotional_delta": emotional_delta,
                "kpis": kpis,
            }, ensure_ascii=False),
            "current_goal": goal_state or "",
            "goal_step": json.dumps(goal_step, ensure_ascii=False) if goal_step else "",
        }
        self.log_cycle_data(cycle_data)
        self._ui_vitals()
        if result.get("success"):
            key = (action.get('verb'), action.get('target'))
            self.recent_success_actions.append(key)
            if len(self.recent_success_actions) > 6:
                self.recent_success_actions.pop(0)
        if self.ui:
            try:
                self.ui.update_kpis(kpis)
                self.ui.set_cycle(self.cycle_counter)
            except Exception:
                pass

    def run_loop(self):
        world = self.world_factory()
        if self.security:
            self.security.update_world(world)
        while self.is_running:
            if self.paused and not self._step_flag:
                time.sleep(0.1)
                continue
            self.cycle_counter += 1
            if self.security:
                self.security.before_cycle(self.cycle_counter)
            world.update()
            self.agent_status['needs']['hunger'] = min(1, self.agent_status['needs']['hunger'] + 0.005)
            ws = world.get_world_state()
            if self.security:
                ws = self.security.modify_world_state(ws)
                try:
                    from adamsec import guards

                    flags = guards.verify_world_state(ws)
                    if flags.get("conflict"):
                        self.security.emit(
                            "security.guard.world_conflict",
                            cycle=self.cycle_counter,
                            location=world.agent_location,
                        )
                except Exception:
                    self.log.debug("Security guard verification failed", exc_info=True)
            full = self.observe(ws)
            impulses = self.orient(full)
            if impulses:
                shift = impulses.get("emotional_shift", {})
                if shift:
                    mood = shift.get("mood")
                    if mood:
                        self.agent_status["emotional_state"]["mood"] = mood
                        self.current_mood = mood
                    d = shift.get("level_delta", 0)
                    lvl = self.agent_status["emotional_state"].get("level", 0.1)
                    lvl = max(0.0, min(1.0, lvl + d))
                    self.agent_status["emotional_state"]["level"] = lvl
                    self.mood_intensity = lvl

                reflection = self.imagine_and_reflect(impulses, world)
                final_action = reflection.get('final_action', {'verb': 'wait', 'target': 'null'})
                reasoning = reflection.get('reasoning', 'I am unsure.')
                emotional_shift = impulses.get('emotional_shift', {})
                if emotional_shift:
                    self.agent_status['emotional_state']['mood'] = emotional_shift.get('mood', self.current_mood)
                    new_level = self.agent_status['emotional_state']['level'] + emotional_shift.get('level_delta', 0)
                    self.agent_status['emotional_state']['level'] = max(0, min(1, new_level))
                self.current_mood = self.agent_status['emotional_state']['mood']
                self.mood_intensity = self.agent_status['emotional_state']['level']
                action, _ = self.decide(final_action, reasoning)
                self.act(world, action, reasoning, full, impulses)
            else:
                self.log.info("Orient failed or empty; waiting.")
                action = {"verb": "wait", "target": "null"}
                self.act(world, action, "No impulses", full, {})
            self.log.info("— Cycle complete. Waiting … —")
            self._ui_status("Cycle complete. Waiting…")
            if self._step_flag:
                self._step_flag = False
                self.paused = True
            # try flushing any pending memory writes periodically
            try:
                if self.memory and hasattr(self.memory, "flush"):
                    self.memory.flush()
            except Exception:
                pass
            time.sleep(self.cycle_sleep)

    # ------------------------------------------------------------------
    def _dampen_repeated_impulses(self, impulses: dict) -> dict:
        items = impulses.get('impulses') or []
        if not items:
            return impulses
        counts = {}
        for verb, target in self.recent_success_actions:
            counts[(verb, target)] = counts.get((verb, target), 0) + 1
        for imp in items:
            verb = imp.get('verb')
            target = imp.get('target')
            streak = counts.get((verb, target), 0)
            if streak >= 2:
                try:
                    urgency = float(imp.get('urgency', 0))
                    imp['urgency'] = max(0.0, urgency * 0.35)
                    imp['dampened'] = True
                except Exception:
                    pass
        return impulses
