# quantum_adam_demo.py
"""
Quantum Adam: Minimal Working Prototype (QuTiP)

This script demonstrates a quantum-inspired decision cycle for Project Adam using QuTiP.
It models:
- Drives as basis states in a Hilbert space
- Adam's mind as a superposition over drives
- Decisions as wavefunction collapse
- Coupled emotions via a Hamiltonian
- Memory/coherence decay via Lindblad operators (decoherence)
- Simple narrative logging across steps

Quickstart (Python 3.10+ recommended):
    pip install qutip numpy matplotlib
    python quantum_adam_demo.py

If you're on Apple Silicon or Windows, see QuTiP install notes:
    https://qutip.org/docs/latest/installation.html

Author: Project Adam
"""

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np

try:
    from qutip import basis, Qobj, ket2dm, mesolve, sigmax, sigmay, sigmaz, qeye
    from qutip import tensor as qtensor
except Exception as e:
    raise SystemExit(
        "QuTiP import failed. Please install QuTiP first:\n"
        "    pip install qutip\n"
        f"Original error: {e}"
    )

# Optional visualization (no specified colors as per style constraints)
import matplotlib.pyplot as plt


# -----------------------------
# Configuration
# -----------------------------
DRIVES = ["curiosity", "hunger", "exploration", "fear"]
DIM = len(DRIVES)  # Hilbert space dimension

# Map an index to drive name and vice versa
IDX2DRIVE = {i: d for i, d in enumerate(DRIVES)}
DRIVE2IDX = {d: i for i, d in enumerate(DRIVES)}


def normalize(vec: np.ndarray) -> np.ndarray:
    nrm = np.linalg.norm(vec)
    return vec if nrm == 0 else vec / nrm


@dataclass
class QuantumAdam:
    """Quantum-inspired Adam agent with a superposed drive state."""
    # Amplitudes for initial superposition over drives, in drive order
    amplitudes: Dict[str, float] = field(default_factory=lambda: {
        "curiosity": 0.7,
        "hunger": 0.1,
        "exploration": 0.2,
        "fear": 0.0,
    })
    # Decoherence strength (0 = none, higher = faster memory fade)
    gamma: float = 0.15
    # Coupling strength between certain drives (entanglement-like coupling term)
    coupling: float = 0.35
    # RNG seed for reproducibility
    seed: int = 42

    def __post_init__(self):
        random.seed(self.seed)
        np.random.seed(self.seed)
        # Build initial ket |psi>
        amp_vec = np.array([self.amplitudes.get(d, 0.0) for d in DRIVES], dtype=np.complex128)
        amp_vec = normalize(amp_vec)
        self.psi = sum(amp_vec[i] * basis(DIM, i) for i in range(DIM))  # Qobj ket
        # Density matrix for open-system evolution
        self.rho = ket2dm(self.psi)
        # Build a simple Hamiltonian coupling some drives (e.g., curiosity<->fear, exploration<->hunger)
        self.H = self._build_hamiltonian(self.coupling)
        # Collapse (Lindblad) operators for decoherence (memory fade / loss of coherence)
        self.c_ops = self._build_decoherence_ops(self.gamma)
        # Narrative log
        self.log: List[str] = []

    def _build_hamiltonian(self, J: float) -> Qobj:
        """
        Construct a simple Hamiltonian that couples pairs of drives.
        Here we couple (curiosity <-> fear) and (exploration <-> hunger).
        """
        # Projectors |i><j| + |j><i| for coupling terms
        def couple(i: int, j: int):
            ket_i = basis(DIM, i)
            ket_j = basis(DIM, j)
            return ket_i * ket_j.dag() + ket_j * ket_i.dag()

        H = 0
        H += J * couple(DRIVE2IDX["curiosity"], DRIVE2IDX["fear"])
        H += J * couple(DRIVE2IDX["exploration"], DRIVE2IDX["hunger"])
        return H

    def _build_decoherence_ops(self, gamma: float) -> List[Qobj]:
        """
        Build Lindblad (collapse) operators. We include amplitude damping-like
        and pure dephasing-like channels across the basis.
        """
        c_ops = []
        if gamma <= 0:
            return c_ops

        # Amplitude damping from each basis state towards |curiosity> (as a soft "ground")
        g = math.sqrt(gamma / max(1, DIM - 1))
        ground = basis(DIM, DRIVE2IDX["curiosity"])
        for i in range(DIM):
            if IDX2DRIVE[i] == "curiosity":
                continue
            excited = basis(DIM, i)
            c_ops.append(g * ground * excited.dag())

        # Dephasing in the drive basis
        for i in range(DIM):
            proj_i = basis(DIM, i) * basis(DIM, i).dag()
            c_ops.append(math.sqrt(gamma * 0.25) * proj_i)

        return c_ops

    def measure_drive(self) -> Tuple[str, float]:
        """
        Perform a projective measurement in the drive basis,
        returning the chosen drive and its probability.
        """
        # Probabilities are diagonal elements of rho in the drive basis
        probs = np.real(np.array([ (basis(DIM, i).dag() * self.rho * basis(DIM, i)).full()[0,0] for i in range(DIM) ]))
        probs = probs / probs.sum() if probs.sum() > 0 else np.ones(DIM) / DIM
        idx = np.random.choice(np.arange(DIM), p=probs)
        chosen = IDX2DRIVE[idx]
        pval = probs[idx]
        # Post-measurement collapse to |idx><idx|
        proj = basis(DIM, idx) * basis(DIM, idx).dag()
        self.rho = proj
        return chosen, float(pval)

    def evolve(self, t_final: float = 1.0, steps: int = 50):
        """
        Open-system evolution under H with decoherence.
        This simulates memory/drive dynamics between action choices.
        """
        tlist = np.linspace(0, t_final, steps)
        result = mesolve(self.H, self.rho, tlist, c_ops=self.c_ops, e_ops=[])
        self.rho = result.states[-1]

    def action_from_drive(self, drive: str) -> str:
        """
        Map the measured drive to a simple action. In a full system this would
        interface with the world model to pick a context-appropriate action.
        """
        mapping = {
            "curiosity": "investigate_window",
            "exploration": "open_door",
            "hunger": "go_to_kitchen",
            "fear": "retreat_from_dark_corner",
        }
        return mapping.get(drive, "idle")

    def step(self, t_final: float = 1.0, steps: int = 50) -> Dict[str, float]:
        """
        One decision cycle: evolve (decohere + couple), then measure, then take action.
        Returns a dict with telemetry for logging.
        """
        self.evolve(t_final=t_final, steps=steps)
        chosen_drive, pval = self.measure_drive()
        action = self.action_from_drive(chosen_drive)
        entry = f"Chose drive={chosen_drive} (p≈{pval:.2f}) → action={action}"
        self.log.append(entry)
        return {
            "drive": chosen_drive,
            "prob": pval,
            "action": action,
        }

    def drive_distribution(self) -> Dict[str, float]:
        """Return current probabilities over drives (diagonal of rho)."""
        diag = np.real(np.diag(self.rho.full()))
        diag = diag / diag.sum() if diag.sum() > 0 else np.ones(DIM) / DIM
        return {IDX2DRIVE[i]: float(diag[i]) for i in range(DIM)}

    def plot_distribution(self, title: str = "Drive distribution"):
        dist = self.drive_distribution()
        labels = list(dist.keys())
        values = [dist[k] for k in labels]

        plt.figure(figsize=(6, 4))
        plt.bar(labels, values)
        plt.ylabel("Probability")
        plt.title(title)
        plt.ylim(0, 1)
        plt.tight_layout()
        plt.show()


def demo(run_steps: int = 8):
    qa = QuantumAdam(
        amplitudes={"curiosity": 0.65, "hunger": 0.15, "exploration": 0.15, "fear": 0.05},
        gamma=0.18,
        coupling=0.30,
        seed=7,
    )

    print("Initial drive distribution:")
    init_dist = qa.drive_distribution()
    for k, v in init_dist.items():
        print(f"  {k:12s}: {v:.3f}")
    print()

    # Plot initial distribution
    try:
        qa.plot_distribution("Initial drive distribution")
    except Exception:
        pass

    # Run decision cycles
    for step_idx in range(run_steps):
        telemetry = qa.step(t_final=0.8, steps=40)
        dist = qa.drive_distribution()
        print(f"[Step {step_idx+1}] {qa.log[-1]}")
        for k, v in dist.items():
            print(f"  {k:12s}: {v:.3f}")
        print()

    # Final plot
    try:
        qa.plot_distribution("Final drive distribution")
    except Exception:
        pass

    # Narrative log
    print("Narrative log:")
    for line in qa.log:
        print(f"  - {line}")


if __name__ == "__main__":
    demo(run_steps=8)
