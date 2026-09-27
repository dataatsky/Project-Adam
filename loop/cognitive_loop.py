import json
import time
from typing import Optional, Callable
import copy
import logging

import config

from text_world import TextWorld, normalize_verb, NULL_TARGETS
from loop.insight_engine import InsightEngine

WAIT_ACTION = {"verb": "wait", "target": None}


class CognitiveLoop:
    """Adam's conscious mind: one OODA cycle per `step()`.

    The world owns Adam's body and mind state (hunger, mood, goal, inventory).
    `agent_status` is a read-only view of it, kept for prompts, UI and API.
    """

    def __init__(self, log_filename, log_headers, ui=None, experiment_tag="baseline", agent_id="adam1", memory=None, psyche=None, world_factory: Optional[Callable[[], TextWorld]] = None):
        self.log = logging.getLogger(__name__ + ".CognitiveLoop")
        # Starting state for a fresh (non-scenario) world, from config.AGENT_STATUS
        self._initial_status = copy.deepcopy(getattr(config, "AGENT_STATUS", {
            "emotional_state": {"mood": "neutral", "level": 0.1},
            "personality": {"curiosity": 0.8, "bravery": 0.6, "caution": 0.7},
            "needs": {"hunger": 0.1},
            "goal": "",
        }))
        self.personality = dict(self._initial_status.get("personality", {}))
        self.world: Optional[TextWorld] = None
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
        self.ui = ui
        self.insight = InsightEngine(history_len=24)
        self.experiment_tag = experiment_tag
        self.agent_id = agent_id
        self.cycle_counter = 0
        self.last_hypothetical = []
        self.world_factory = world_factory or TextWorld
        self.imagine_top_k = int(getattr(config, "IMAGINE_TOP_K", 3))
        self.tom_interval = int(getattr(config, "TOM_INTERVAL", 5))
        try:
            self.cycle_sleep = float(getattr(config, "CYCLE_SLEEP", 5.0))
        except Exception:
            self.cycle_sleep = 5.0
        self.security = None
        self.recent_success_actions: list[tuple[str | None, str | None]] = []
        self.last_impulses: list[dict] = []
        self.diary_entries: list[dict] = []
        self.tom_cache: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # State (read from the world)
    def _agent(self) -> Optional[dict]:
        if self.world is None:
            return None
        return self.world.agents.get(self.agent_id)

    @property
    def agent_status(self) -> dict:
        agent = self._agent()
        if not agent:
            return copy.deepcopy(self._initial_status)
        goal = agent.get("active_goal")
        return {
            "emotional_state": {"mood": agent["mood"], "level": agent["mood_intensity"]},
            "personality": dict(self.personality),
            "needs": {"hunger": agent["hunger"]},
            "goal": goal["name"] if goal else None,
        }

    @property
    def current_mood(self) -> str:
        return self.agent_status["emotional_state"]["mood"]

    @property
    def mood_intensity(self) -> float:
        return float(self.agent_status["emotional_state"]["level"])

    def attach_world(self, world: TextWorld):
        """Bind the loop to a world.

        A fresh default world gets Adam's configured starting state; a scenario
        world keeps the state the scenario defines.
        """
        self.world = world
        seed = self.agent_id not in world.agents or not world.scenario_name
        world.add_agent(self.agent_id)
        if seed:
            status = self._initial_status
            agent = world.agents[self.agent_id]
            agent["hunger"] = float(status.get("needs", {}).get("hunger", agent["hunger"]))
            agent["mood"] = status.get("emotional_state", {}).get("mood", agent["mood"])
            agent["mood_intensity"] = float(status.get("emotional_state", {}).get("level", agent["mood_intensity"]))
            if status.get("goal") and not agent["active_goal"]:
                world.set_goal(status["goal"], agent_id=self.agent_id)
        if self.security:
            self.security.update_world(world)

    def attach_security(self, security):
        self.security = security
        if hasattr(self.security, "context"):
            self.security.context.loop = self
        if self.world is not None:
            self.security.update_world(self.world)

    def log_cycle_data(self, cycle_data):
        import csv
        try:
            with open(self.log_filename, mode="a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.log_headers)
                if f.tell() == 0:
                    writer.writeheader()
                writer.writerow(cycle_data)
        except Exception as e:
            self.log.warning(f"CSV write error: {e}")

    # helpers to touch UI
    def _ui_status(self, txt):
        if self.ui:
            self.ui.set_status(txt)

    def _ui_vitals(self):
        if self.ui:
            status = self.agent_status
            self.ui.update_vitals(
                status['emotional_state']['mood'],
                status['emotional_state']['level'],
                status['needs']['hunger']
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
        self.log.debug(json.dumps(world_state, indent=2, default=str))
        self.current_world_state = world_state
        self._ui_vitals()
        return world_state

    def orient(self, world_state, world: Optional[TextWorld] = None):
        self._ui_status("Orienting (Subconscious)…")
        self.log.info("— 2. ORIENTING —")
        world = world or self.world
        sensory = world_state.get("sensory_events", [])
        current_goal = world_state.get("goal") or "None"
        location = world_state.get("agent_location") or "Unknown"

        # Contextual retrieval: query memory with location, goal and salient objects
        objects_query = " ".join([f"{e.get('type','')} {e.get('object','')}" for e in sensory if 'object' in e])
        query_text = f"Context: {location}, Goal: {current_goal}. Sensory: {objects_query}"
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
            "recent_diaries": [entry.get("text") for entry in self.diary_entries[-3:]],
            "mastered_skills": self.insight.get_mastered_skills() if self.insight else [],
        }
        if self.security:
            payload = self.security.before_psyche("generate_impulse", payload)
        impulses = None
        if self.psyche:
            impulses = self.psyche.generate_impulse(payload)
        if self.security:
            impulses = impulses or {}
            self.security.after_psyche("generate_impulse", payload, impulses)
        if not impulses:
            self.last_impulses = []
            return impulses
        impulses = self._ground_impulses(impulses, world)
        impulses = self._dampen_repeated_impulses(impulses)
        self.last_impulses = impulses.get("impulses", []) or []
        self.ui and self.ui.set_subconscious(
            impulses.get("emotional_shift", {}),
            impulses.get("impulses", []),
            self.last_resonant_memories,
        )
        return impulses

    def _ground_impulses(self, impulses: dict, world: Optional[TextWorld]) -> dict:
        """Drop impulses the world cannot execute (unknown verbs, unseen targets)."""
        items = impulses.get("impulses") or []
        if world is None:
            return impulses
        grounded = []
        for imp in items:
            if not isinstance(imp, dict):
                continue
            imp = {**imp, "verb": normalize_verb(imp.get("verb"))}
            ok, why = world.validate_action(imp, self.agent_id)
            if ok:
                grounded.append(imp)
            else:
                self.log.info(f"Dropped ungrounded impulse {imp.get('verb')} {imp.get('target')}: {why}")
        return {**impulses, "impulses": grounded or [{**WAIT_ACTION, "drive": "safety", "urgency": 0.1}]}

    def _update_theory_of_mind(self) -> list[str]:
        """Model other agents present, when they spoke or the model is stale."""
        if not self.psyche or not hasattr(self.psyche, "theory_of_mind"):
            return []
        events = self.current_world_state.get("sensory_events", [])
        present = [e.get("object") for e in events if e.get("type") == "visual" and e.get("object") != self.agent_id]
        for other in present:
            said = [e.get("details", "") for e in events if e.get("type") == "auditory" and e.get("object") == other]
            cached = self.tom_cache.get(other)
            stale = not cached or self.cycle_counter - cached["cycle"] >= self.tom_interval
            if not said and not stale:
                continue
            tom = self.psyche.theory_of_mind(
                other_agent_id=other,
                environment_desc=self.current_world_state.get("agent_location", "unknown"),
                recent_actions="; ".join(said) or f"{other} is standing here silently.",
                relationship_context=cached["insight"] if cached else "We have not interacted before.",
            )
            if tom:
                insight = f"ToM({other}): Beliefs={tom.get('beliefs')}, Goal={tom.get('predicted_goal')}, Trust={tom.get('trust_level')}, Threat={tom.get('potential_threat')}"
                self.tom_cache[other] = {"cycle": self.cycle_counter, "insight": insight}
        return [self.tom_cache[o]["insight"] for o in present if o in self.tom_cache]

    def imagine_and_reflect(self, initial_impulses, world: TextWorld):
        self._ui_status("Imagining & Reflecting…")
        self.log.info("— 2.5. IMAGINE & REFLECT —")
        hypothetical = []
        top = sorted(initial_impulses.get("impulses", []), key=lambda x: x.get("urgency", 0), reverse=True)[: self.imagine_top_k]

        actions_to_imagine = [
            {"verb": imp.get("verb"), "target": imp.get("target"), "instrument": imp.get("instrument")}
            for imp in top if isinstance(imp, dict)
        ]

        # Parallel Imagination (Batch Call)
        if self.psyche and actions_to_imagine:
            imagined_results = self.psyche.imagine_batch(actions_to_imagine)
        else:
            imagined_results = ["My imagination is fuzzy." for _ in actions_to_imagine]

        # Simulation
        for i, action in enumerate(actions_to_imagine):
            sim = world.clone().process_action(action, agent_id=self.agent_id)
            hypothetical.append({
                "action": action,
                "imagined": imagined_results[i] if i < len(imagined_results) else "Error",
                "simulated": sim.get("reason"),
            })
        self.last_hypothetical = hypothetical
        self.ui and self.ui.set_imagination(hypothetical)

        tom_insights = self._update_theory_of_mind()
        payload = {
            "current_state": self.agent_status,
            "world_state": self.current_world_state,
            "hypothetical_outcomes": hypothetical,
            "recent_memories": self.recent_memories + tom_insights,
        }
        reflection = {"final_action": dict(WAIT_ACTION), "reasoning": "Mind is blank."}
        if self.psyche:
            if self.security:
                payload = self.security.before_psyche("reflect", payload)
            reflection = self.psyche.reflect(payload) or reflection
            self.log.debug(f"Reflection: {reflection.get('reasoning')}")
            if reflection.get("thoughts_on_others") and tom_insights:
                self.log.info(f"Theory of Mind: {reflection.get('thoughts_on_others')}")
                self._ui_status(f"Thinking about others: {reflection.get('thoughts_on_others')}")
        if self.security:
            self.security.after_psyche("reflect", payload, reflection)

        self._update_goal(reflection, world)
        return reflection

    def _update_goal(self, reflection: dict, world: TextWorld):
        """Apply goal completion/abandonment and adopt a proposed goal when free."""
        agent = world.agents.get(self.agent_id)
        if not agent:
            return
        status = reflection.get("goal_status")
        if agent["active_goal"] and status in {"completed", "abandoned"}:
            self.log.info(f"Goal '{agent['active_goal']['name']}' {status}.")
            world.clear_goal(self.agent_id, status=status)
        new_goal = reflection.get("new_goal")
        if new_goal and not agent["active_goal"]:
            steps = reflection.get("new_goal_plan")
            self.log.info(f"Psyche proposed new goal: {new_goal} with plan: {steps}")
            world.set_goal(new_goal, steps=steps, agent_id=self.agent_id)

    def _choose_action(self, reflection: dict, impulses: dict, world: TextWorld) -> tuple[dict, str]:
        """Take the reflected decision if the world can execute it; else the best grounded impulse."""
        final = dict(reflection.get("final_action") or WAIT_ACTION)
        final["verb"] = normalize_verb(final.get("verb"))
        reasoning = reflection.get("reasoning") or "I am unsure."
        ok, why = world.validate_action(final, self.agent_id)
        if ok:
            return final, reasoning
        self.log.info(f"Rejected ungrounded decision {final.get('verb')} {final.get('target')}: {why}")
        ranked = sorted(impulses.get("impulses", []), key=lambda x: x.get("urgency", 0), reverse=True)
        fallback = next((imp for imp in ranked if world.validate_action(imp, self.agent_id)[0]), WAIT_ACTION)
        action = {k: fallback.get(k) for k in ("verb", "target", "instrument") if fallback.get(k) is not None}
        return action, f"{reasoning} (I wanted to {final.get('verb')} {final.get('target')}, but {why} So I followed my strongest urge instead.)"

    def decide(self, final_action, reasoning):
        self._ui_status("Deciding…")
        self.log.info("— 3. DECIDING —")
        self.log.debug(f"Chosen: {final_action}")
        self.ui and self.ui.set_decision(final_action, reasoning)
        return final_action, reasoning

    def act(self, world, action, reasoning, world_state, impulses):
        self._ui_status("Acting…")
        self.log.info("— 4. ACTING —")
        result = world.process_action(action, agent_id=self.agent_id)
        self.log.debug(f"Result: {result}")
        # Narrative memory
        target = action.get('target')
        sensed_objs = [e['object'] for e in world_state.get('sensory_events', []) if 'object' in e]
        sensed_str = f"I sensed {', '.join(sensed_objs)}." if sensed_objs else "I sensed nothing unusual."
        decision_str = f"I decided to {action['verb']}" if target in NULL_TARGETS else f"I decided to {action['verb']} the {target}"
        reason = result.get('reason', 'it just happened.')
        loc_name = world_state.get("agent_location", "unknown place")
        event_desc = (
            f"I was in the {loc_name}. {sensed_str} My emotional state became {self.current_mood}. "
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

        # Consolidation (Sleep)
        if action.get("verb") == "sleep" and result.get("success"):
            self.log.info("Agent is sleeping... Triggering memory consolidation.")
            try:
                if self.psyche and hasattr(self.psyche, "consolidate"):
                    insight = self.psyche.consolidate(self.recent_memories[-10:])
                    if insight:
                        self.log.info(f"Consolidated Insight: {insight}")
                        if self.memory:
                            self.memory.upsert_texts([f"INSIGHT: {insight}"])
                        self.recent_memories.append(f"Upon waking, I realized: {insight}")
            except Exception as e:
                self.log.error(f"Consolidation failed: {e}")

        # --- Insights & snapshot ---
        triggers = [f"{e.get('object')} : {e.get('details')}" for e in world_state.get('sensory_events', []) if 'object' in e]
        imps = impulses.get('impulses', []) if impulses else []
        emotional_delta = (impulses or {}).get('emotional_shift', {})
        self.insight.add_cycle(action=action, success=bool(result.get('success')), impulses=imps, triggers=triggers, mood=self.current_mood)
        kpis = self.insight.compute_kpis()
        imagined_texts = []
        for hypo in self.last_hypothetical or []:
            act = hypo.get('action', {}) or {}
            verb = act.get('verb') or 'wait'
            tgt = act.get('target') or 'null'
            imagined_texts.append(f"{verb} {tgt}: {hypo.get('imagined', '')}")
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
            "location": world_state.get("agent_location"),
            "mood": self.current_mood,
            "mood_intensity": self.mood_intensity,
            "sensory_events": json.dumps(world_state.get('sensory_events', []), ensure_ascii=False),
            "resonant_memories": json.dumps(self.last_resonant_memories, ensure_ascii=False),
            "impulses": json.dumps(imps, ensure_ascii=False),
            "chosen_action": f"{action.get('verb')}_{action.get('target')}",
            "action_result": json.dumps(result, ensure_ascii=False, default=str),
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
        return result

    # ------------------------------------------------------------------
    def step(self, world: Optional[TextWorld] = None):
        """Run one full OODA cycle against an already-advanced world.

        Returns (action, result). Used by `run_loop` and by `benchmark.py`,
        so live runs and benchmarks exercise exactly the same cognition.
        """
        world = world or self.world
        if world is not self.world:
            self.attach_world(world)
        self.cycle_counter += 1
        if self.security:
            self.security.before_cycle(self.cycle_counter)
        ws = world.get_world_state(agent_id=self.agent_id)
        if self.security:
            ws = self.security.modify_world_state(ws)
            try:
                from adamsec import guards

                flags = guards.verify_world_state(ws)
                if flags.get("conflict"):
                    self.security.emit(
                        "security.guard.world_conflict",
                        cycle=self.cycle_counter,
                        location=ws.get("agent_location"),
                    )
            except Exception:
                self.log.debug("Security guard verification failed", exc_info=True)
        full = self.observe(ws)
        impulses = self.orient(full, world)
        if impulses:
            shift = impulses.get("emotional_shift") or {}
            if shift:
                world.apply_emotional_shift(self.agent_id, shift.get("mood"), shift.get("level_delta", 0))
            reflection = self.imagine_and_reflect(impulses, world)
            action, reasoning = self._choose_action(reflection, impulses, world)
            action, _ = self.decide(action, reasoning)
            result = self.act(world, action, reasoning, full, impulses)
        else:
            self.log.info("Orient failed or empty; waiting.")
            action = dict(WAIT_ACTION)
            result = self.act(world, action, "No impulses", full, {})
        # try flushing any pending memory writes periodically
        try:
            if self.memory and hasattr(self.memory, "flush"):
                self.memory.flush()
        except Exception:
            pass
        self._maybe_self_reflect()
        return action, result

    def run_loop(self):
        world = self.world or self.world_factory()
        self.attach_world(world)
        while self.is_running:
            if self.paused and not self._step_flag:
                time.sleep(0.1)
                continue
            for event in world.update():
                self.log.info(f"World: {event}")
            self.step(world)
            self.log.info("— Cycle complete. Waiting … —")
            self._ui_status("Cycle complete. Waiting…")
            if self._step_flag:
                self._step_flag = False
                self.paused = True
            time.sleep(self.cycle_sleep)

    # ------------------------------------------------------------------
    def _maybe_self_reflect(self):
        if self.cycle_counter <= 0 or self.cycle_counter % 5 != 0:
            return

        kpis = self.insight.compute_kpis() if self.insight else {}
        diary_text = (
            f"Cycle {self.cycle_counter}: Mood {self.current_mood} (intensity {self.mood_intensity:.2f}); "
            f"Recent action: {self.recent_memories[-1] if self.recent_memories else 'none'}; "
            f"Frustration {kpis.get('frustration')}; Goal progress {kpis.get('goal_progress')}"
        )
        entry = {"cycle": self.cycle_counter, "text": diary_text}
        self.diary_entries.append(entry)
        if len(self.diary_entries) > 10:
            self.diary_entries.pop(0)
        self.recent_memories.append(f"Diary entry: {diary_text}")
        if len(self.recent_memories) > 5:
            self.recent_memories.pop(0)
        try:
            if self.memory:
                self.memory.upsert_texts([diary_text])
        except Exception:
            pass

        # Adjust mood slightly based on reflection outcome
        if self.world is not None:
            frustration = kpis.get('frustration', 0)
            if frustration and frustration > 0.6:
                self.world.apply_emotional_shift(self.agent_id, "determined", 0.05)
            else:
                self.world.apply_emotional_shift(self.agent_id, None, -0.02)

    # ------------------------------------------------------------------
    def _dampen_repeated_impulses(self, impulses: dict) -> dict:
        items = impulses.get('impulses') or []
        if not items:
            return impulses
        counts = {}
        for verb, target in self.recent_success_actions:
            counts[(verb, target)] = counts.get((verb, target), 0) + 1
        for imp in items:
            streak = counts.get((imp.get('verb'), imp.get('target')), 0)
            if streak >= 2:
                try:
                    imp['urgency'] = max(0.0, float(imp.get('urgency', 0)) * 0.35)
                    imp['dampened'] = True
                except Exception:
                    pass
        return impulses
