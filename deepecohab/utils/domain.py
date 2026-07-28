from __future__ import annotations
from dataclasses import dataclass, field
import datetime as dt
import polars as pl

@dataclass(frozen=True, slots=True)
class Project:
    name: str
    experiments: dict[str, Experiment]

@dataclass(frozen=True, slots=True)
class Experiment:
    name: str
    start: dt.datetime
    end: dt.datetime | None
    light_start: str
    dark_start: str
    recording_timezone: str
    animals: dict[str, Animal]
    layout: Layout

@dataclass(frozen=True, slots=True)
class Animal:
    tag_no: str                      
    sex: str | None = None
    age: pl.duration
    genetic_background: str | None = None
    mouse_line: str | None = None
    genotype: str | None = None
    treatment: str | None = None
    notes: str = ""


@dataclass(frozen=True, slots=True)
class Cage:
    id: str                          
    cage_no: int                   
    cage_type: str                   

@dataclass(frozen=True, slots=True)
class Tunnel:
    id: str                          
    name: str                        
    endpoints: frozenset[str]        
    antennas: dict[str, int]   
    is_deadend: bool = False      

Position = Cage | Tunnel

@dataclass(frozen=True, slots=True)
class Antenna:
    id: int                          
    tunnel_id: str
    cage_id: str


@dataclass(frozen=True, slots=True)
class Crossing:
    tunnel_id: str
    from_cage_id: str
    to_cage_id: str

@dataclass
class Layout:
    cages: dict[str, Cage]
    tunnels: dict[str, Tunnel]
    antennas: dict[int, Antenna]

    _pairs: dict[tuple[int, int], Cage | Crossing] = field(default_factory=dict)

    @property
    def pairs(self) -> dict[tuple[int, int], Cage | Crossing]:
        return self._pairs

    def classify(self, a_from: int, a_to: int) -> Cage | Crossing | None:
        """Resolve an ordered antenna pair to Cage or Crossing."""
        return self._pairs.get((a_from, a_to))

    def tunnel_between(self, cage_a: str, cage_b: str) -> Tunnel | None:
        want = frozenset({cage_a, cage_b})
        return next((t for t in self.tunnels.values() if t.endpoints == want), None)

    def validate(self) -> None:
        for t in self.tunnels.values():
            assert len(t.endpoints) == 2, f"{t.id} must join two distinct cages"
            for cid in t.endpoints:
                assert cid in self.cages, f"{t.id} references unknown {cid}"
        for a in self.antennas.values():
            assert a.tunnel_id in self.tunnels, f"antenna {a.id} bad tunnel"
            assert a.cage_id in self.cages, f"antenna {a.id} bad cage"

    def to_dimension_frames(self) -> dict:
        cages = pl.DataFrame([{"cage_id": c.id, "cage_no": c.cage_no,
                               "cage_type": c.cage_type}
                              for c in self.cages.values()]).sort("cage_no")
        antennas = pl.DataFrame([{"antenna_id": a.id, "tunnel_id": a.tunnel_id,
                                  "cage_id": a.cage_id}
                                 for a in self.antennas.values()]).sort("antenna_id")
        return {"cages": cages, "antennas": antennas}

    

def location_kind(p: Position) -> str:
    return "cage" if isinstance(p, Cage) else "tunnel"