# Project Adam: Operator's Manual

This manual provides detailed instructions for running, testing, benchmarking, and extending Project Adam.

---

## 🏗️ Part 1: Setup & Installation

### 1. Requirements
*   **OS**: macOS (recommended), Linux, or Windows.
*   **Python**: 3.10 or higher.
*   **Ollama**: Installed and running (`ollama serve`).
*   **Git**: For version control.

### 2. Installation
1.  **Clone the repository**:
    ```bash
    git clone https://github.com/your-repo/project-adam.git
    cd project-adam
    ```

2.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Environment Configuration**:
    Copy the example file and configure it:
    ```bash
    cp .env.example .env
    ```
    **Critical Settings in `.env`**:
    *   `PSYCHE_LLM_API_URL=http://127.0.0.1:5001/` (Note: Port 5001 is default to avoid macOS AirPlay conflict).
    *   `OLLAMA_MODEL=qwen2.5:14b` (or `llama3`).
    *   `PINECONE_API_KEY=...` (Optional, for long-term memory).

---

## 🚀 Part 2: Operating the System

Project Adam consists of two parts: the **Psyche Service** (Subconscious/LLM) and the **Cognitive Loop** (Conscious/World).

### 1. Start the Psyche Service
This service handles all LLM interactions, templating, and structured output enforcement.

```bash
python psyche_ollama.py
```
*   **Success**: You should see `Running on http://127.0.0.1:5001`.
*   **Note**: Leave this terminal open running in the background.

### 2. Start the Agent (GUI Mode)
This launches the visual interface where you can watch Adam think and act.

```bash
python main.py
```
*   **The Interface**:
    *   **Log**: Real-time narrative of the world ("Adam moves north.").
    *   **Vitals**: Hunger, Mood, Goal.
    *   **Tabs**: Inspect internal state (Impulses, Reflections, Plans).

### 3. Start the Agent (Headless Mode)
Ideal for long runs or background execution without window management.

```bash
python main.py --headless --cycles 50
```
*   `--cycles N`: Stop after N cognitive cycles.
*   `--api-port N`: Expose a status API (default 8080) for external monitoring.

---

## 📊 Part 3: Benchmarking & Evaluation

Verified intelligence is a core tenet of Project Adam. Use the headless benchmark tool to run standardized scenarios.

### 1. Running a Benchmark
The `benchmark.py` tool loads a scenario, creates a pristine world, and runs the agent until a Win/Fail condition is met.

```bash
# Run the 'Hunger Test' 5 times
python benchmark.py --scenario hunger_test --runs 5
```

### 2. Available Scenarios
Scenarios are located in the `scenarios/` directory.
*   `hunger_test`: Agent starts with high hunger. Win = Eats food before starving (20 cycles).
*   `locked_room`: Agent interacts with obstacles. Win = Escapes.
*   `social_party`: Multi-agent interaction. Win = Gains trust of peers.

### 3. Interpreting Output
```text
Run 1/5... [WIN] in 8 cycles.
Run 2/5... [WIN] in 6 cycles.
...
Success Rate: 100.0% (5/5)
Avg Cycles (Wins): 7.0
```
*   **High Success Rate**: Reliable planning and agency.
*   **Low Cycle Count**: Efficient intelligence (didn't wander aimlessly).

---

## 🛠️ Part 4: Testing

### 1. Unit Tests
Run the standard pytest suite to verify logic stability.

```bash
pytest
```
**Key Suites**:
*   `tests/test_text_world.py`: Grid physics, objects.
*   `tests/test_psyche_api.py`: LLM contracts (mocked).
*   `tests/test_planning_and_skills.py`: Goal hierarchy and learning.

### 2. Manual Verification
Sometimes you need to verify "vibes" or non-deterministic behavior.
1.  Run `python main.py`.
2.  Open the **Subconscious** tab.
3.  Pause the loop after an action.
4.  Check if the `emotional_shift` matches the context (e.g., Eating food should increase "Joy").

---

## 🧬 Part 5: Development & Extensions

### 1. How to Create a New Agent
To add a second agent (e.g., "Eve") to the simulation:

**A. dynamic Injection (Runtime)**
You can add agents programmatically if you are writing a custom script or scenario:

```python
# In your custom script
world.add_agent("eve1")
world.agents["eve1"]["pos"] = (1, 1)  # Set location
```

**B. Configuration (Static)**
Edit `text_world.py` or your scenario file to initialize them by default.

### 2. How to Create a New Scenario
Create a python file in `scenarios/`, e.g., `scenarios/escape_room.py`.

```python
from text_world import TextWorld

def check_win(world: TextWorld):
    # Win if agent is at specific coordinates with a specific item
    agent = world.agents.get("adam1")
    if agent and agent['pos'] == (5, 5) and "gold_key" in agent['inventory']:
        return True
    return False

CONFIG = {
    "name": "escape_room",
    "description": "Find the key and exit.",
    "max_cycles": 25,
    "map_layout": {
        "rooms": [
            {"coords": (0, 0), "name": "Cell", "desc": "A dark cell.", "objects": {
                "gold_key": {"type": "key", "state": "exist"}
            }},
            {"coords": (5, 5), "name": "Exit", "desc": "Freedom."}
        ]
    },
    "win_condition": check_win
}
```

### 3. Customizing Personality
Adam's personality is defined in **Jinja2 Templates**.
*   **File**: `templates/subconscious.j2`
*   **Action**: Edit the `System Prompt` section.
    *   *Example*: Change "You are a rational agent" to "You are a nervous, paranoid survivalist."
*   **Effect**: Restart `psyche_ollama.py` to apply changes.

### 4. Adding New Tools/Physics
1.  **Define the Verb**: Add `_act_paint` to `TextWorld` class.
2.  **Define the Physics**:
    ```python
    def _act_paint(self, agent_id, target, color):
        # Update object properties
        pass
    ```
3.  **Update Psyche**: Add `paint` to the valid verbs list in `templates/subconscious.j2`.

---

## ❓ Troubleshooting

**Q: Connection Refused on http://127.0.0.1:5000**
*   **A**: macOS uses port 5000 for AirPlay. We default to **5001**. Ensure `PSYCHE_LLM_API_URL` in `.env` is set to `http://127.0.0.1:5001/`.

**Q: Benchmark fails with 403 Forbidden**
*   **A**: This usually means the client is trying to hit port 5000 while the server is on 5001 (or vice versa). Check `config.py` matches your running `psyche_ollama.py` instance.

**Q: "Read timed out" during benchmark**
*   **A**: Local LLMs can be slow. Edit `config.py` -> `PSYCHE_TIMEOUT` and increase it (e.g., to 60 or 120 seconds).
