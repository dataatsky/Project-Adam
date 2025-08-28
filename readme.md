Project Adam: Documentation
Welcome to Project Adam, a simulation designed to explore the principles of emergent AI behavior. This document provides a comprehensive guide to understanding, running, and analyzing the project.

1. Introduction
Project Adam is a Python-based simulation of an Emergent Behavior Agent (EBA) named Adam. Unlike traditional, scripted AI characters, Adam's actions are not predetermined. Instead, his behavior emerges from a set of core psychological drives, a persistent memory, and his real-time perception of a simulated world.

The goal of this project is to create a believable, non-player character (NPC) whose personality and habits develop organically over time based on his unique experiences.

2. Core Concepts
The architecture of Project Adam is built on four key components that work together to simulate a mind.

The Text World (text_world.py): This is Adam's entire reality. It's a simple, text-based simulation of a small apartment with multiple rooms and interactive objects. The world runs its own clock, triggers random events (like a ringing phone), and enforces the rules of the environment.

The Psyche-LLM (psyche_llm_mock.py or psyche_llm_ollama.py): This acts as Adam's subconscious. It generates raw, unfiltered impulses based on Adam's current situation, his memories, and his core drives. You can run a simple mock version or a more advanced version powered by a real, local Large Language Model.

The Memory (Pinecone Database): Adam's long-term memory is stored in a cloud-based vector database. Every significant experience is converted into a text description and saved. When Adam perceives a new event, his brain queries this database to find semantically similar past experiences, which then influence his emotional response.

The Cognitive Loop (cognitive_loop_gui.py): This is Adam's conscious mind and central nervous system. It runs a continuous loop that connects all other parts:

It Observes the state of the Text World.

It Orients itself by retrieving relevant memories and getting impulses from the Psyche-LLM.

It Decides on a final action by weighing the competing impulses against its personality traits.

It Acts by sending a command back to the Text World.

Finally, it forms a new memory of the entire experience.

3. System Architecture
The project consists of three main Python scripts that must be run simultaneously. They communicate with each other over local network requests (HTTP).

The Psyche-LLM: Runs a Flask web server that exposes a single API endpoint. It waits for requests from the Cognitive Loop. You will run either the mock or the Ollama version.

cognitive_loop_gui.py: This is the main script. It runs the core logic in a background thread and displays the Psyche Monitor GUI. It sends requests to the Psyche-LLM and manages the connection to the Pinecone memory database.

text_world.py: This is not run as a separate script but is instantiated as a class within the cognitive_loop_gui.py's background thread.

4. Component Deep Dive
psyche_llm_ollama.py
This script is the most complex component, acting as the bridge to the local LLM and serving as Adam's entire mind—from raw emotion to logical thought. It is a Flask server that uses the official ollama library to communicate with the language model. It exposes three distinct endpoints, each with a unique persona defined by a system prompt.

/generate_impulse (The Subconscious): This endpoint receives the current world state and memories. Its prompt instructs the LLM to act as Adam's raw, unfiltered subconscious, generating a list of creative, sometimes illogical, impulses based on a "toolbox" of verbs and the nouns it can perceive.

/imagine (The Imagination): This endpoint receives a single hypothetical action (e.g., "use book on door"). Its prompt instructs the LLM to act as Adam's imagination, predicting a plausible narrative outcome for that action.

/reflect (The Conscious Mind): This endpoint receives the results from the imagination/simulation phase. Its prompt is the most advanced, instructing the LLM to act as Adam's rational, conscious mind. It must analyze the hypothetical outcomes, weigh them against its long-term goals and emotional state, and make a final, logical decision.

5. Setup and Installation
Follow these steps to get Project Adam running on your machine.

Step 1: Install Dependencies
You will need Python 3 installed. Open your terminal and install the required libraries:

pip install requests flask sentence-transformers pinecone-client pandas matplotlib seaborn ollama


Step 2: Set Up Pinecone
Adam's memory requires a free Pinecone account.

Go to Pinecone.io and sign up.

In your dashboard, click "Create Index".

Use the following configuration:

Index Name: project-adam-memory-text

Dimensions: 384

Metric: cosine

Click on "API Keys" in the sidebar to find your API Key and Environment name.

Step 3: Configure the Script
Open cognitive_loop_gui.py in a text editor and replace the placeholder values with your Pinecone credentials.

6. Running the Simulation
You have two options for running the simulation.

Option A: Basic Simulation (Mock LLM)
This is the simplest way to run the project without needing powerful hardware.

Start the Subconscious: Open a terminal and run: python psyche_llm_mock.py

Start Adam's Mind: Open a second terminal and run: python cognitive_loop_gui.py

Option B: Advanced Simulation (Ollama LLM)
This option uses a real language model for much more complex behavior but requires a more powerful computer.

Install and Run Ollama:

Download and install Ollama from ollama.com.

Open your terminal and pull a model. We recommend starting with a small one: ollama pull llama3:8b

Ensure the Ollama application is running in the background.

Start the Subconscious: Open a terminal and run the new script:

python psyche_llm_ollama.py


Note: You can edit this file to change which Ollama model you want to use.

Start Adam's Mind: Open a second terminal and run:

python cognitive_loop_gui.py


7. Understanding the Output
You can monitor Adam's existence in three ways:

Console Output: The terminal running cognitive_loop_gui.py will print the detailed, step-by-step process of Adam's OODA loop for every cycle.

Psyche Monitor GUI: This window provides a real-time, at-a-glance view of Adam's internal state.

Behavior Log (adam_behavior_log.csv): Every thought cycle is saved as a new row in this CSV file.

8. Observing Emergent Behavior
The primary goal of Project Adam is to observe behaviors that were not explicitly programmed. As you watch the simulation, you will notice Adam developing unique habits, quirks, and coping mechanisms.

Cognitive Overload / Analysis Paralysis
One of the most interesting emergent behaviors you might observe is Adam's response to a chaotic environment.

If the text_world triggers multiple high-priority events at once (e.g., the phone rings, the door knocks, and the TV turns on to static), you may see Adam's emotional state become "confused" or "anxious." His final decision in such a cycle is often to simply wait.

This is not a bug. It is a realistic simulation of cognitive overload. When faced with too many competing priorities, the most logical response can be to freeze and do nothing rather than make a potentially wrong choice. This "analysis paralysis" is a sign that Adam's mind is complex enough to recognize an overwhelming situation and react in a psychologically plausible way.

Delusional Obsession / Wishful Thinking
With the introduction of the Imagination Engine, you may observe a fascinating, human-like flaw in Adam's reasoning.

If Adam is in an idle state with a strong, unfulfilled long-term goal (like "find the source of the strange noises"), his Imagination Engine may invent creative but false possibilities to justify an action. For example, he might repeatedly try to investigate the fridge, with his imagination suggesting it could contain a "hidden clue" or a "secret message."

His conscious mind then sees two conflicting pieces of information: the boring, real outcome from the simulation ("nothing happens") and the exciting, imagined outcome. If his curiosity and drive to achieve his goal are strong enough, he may choose to believe his imagination over reality.

This is a form of AI delusion. He becomes trapped in a loop of wishful thinking, repeatedly trying a failed action because the imagined possibility is more compelling than the mundane truth. This demonstrates a complex interplay between creativity, goals, and the ability to learn from negative feedback.

9. Analyzing Adam's Behavior
After you've let the simulation run for a while, stop the scripts and run the analysis script in your terminal:

python analyze_behavior.py


This will generate plots of Adam's behavior, saved as .png files.