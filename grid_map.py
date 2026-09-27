from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

Coord = Tuple[int, int]


@dataclass
class Location:
    name: str
    description: str
    objects: Dict[str, Dict] = field(default_factory=dict)
    visited: bool = False


class GridMap:
    def __init__(self):
        # (x, y) -> Location
        # Standard Cartesian: North (+y), South (-y), East (+x), West (-x)
        self.grid: Dict[Coord, Location] = {}
        # frozenset({a, b}) -> door object dict (shared with the room objects)
        self.doors: Dict[frozenset, Dict] = {}

        # Define offsets for cardinal directions
        self.offsets = {
            "north": (0, 1),
            "south": (0, -1),
            "east": (1, 0),
            "west": (-1, 0)
        }

    def add_location(self, x: int, y: int, name: str, description: str, objects: Dict[str, Dict] = None):
        if objects is None:
            objects = {}
        self.grid[(x, y)] = Location(name, description, objects)

    def get_location(self, x: int, y: int) -> Optional[Location]:
        return self.grid.get((x, y))

    def add_door(self, a: Coord, b: Coord, door: Dict):
        """Register a door on the edge between two adjacent cells."""
        self.doors[frozenset((tuple(a), tuple(b)))] = door

    def door_between(self, a: Coord, b: Coord) -> Optional[Dict]:
        return self.doors.get(frozenset((tuple(a), tuple(b))))

    def get_exits(self, x: int, y: int) -> List[str]:
        """Return list of valid cardinal directions from (x, y)."""
        valid_exits = []
        for direction, (dx, dy) in self.offsets.items():
            if (x + dx, y + dy) in self.grid:
                valid_exits.append(direction)
        return valid_exits

    def move(self, x: int, y: int, direction: str) -> Optional[Tuple[int, int]]:
        """Return new coordinates if valid move, else None."""
        direction = direction.lower()
        if direction not in self.offsets:
            return None

        dx, dy = self.offsets[direction]
        target = (x + dx, y + dy)

        if target not in self.grid:
            return None
        door = self.door_between((x, y), target)
        if door and door.get("state") == "locked":
            return None
        return target
