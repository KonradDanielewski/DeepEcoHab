from __future__ import annotations
from dataclasses import dataclass, field
import datetime as dt



@dataclass(frozen=True, slots=True)
class Animal:
    tag_no: str                      
    sex: str | None = None
    age: dict[int, str] = None
    dob: dt.datetime = None
    genetic_background: str | None = None
    mouse_line: str | None = None
    genotype: str | None = None
    treatment: str | None = None
    notes: str = ""


@dataclass(frozen=True, slots=True)
class Cage:
    id: str                          
    cage_no: int
    cell_id: str                     
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
    adjacent_cage_id: str
    side: str                        


@dataclass(frozen=True, slots=True)
class Crossing:
    tunnel_id: str
    from_cage_id: str
    to_cage_id: str

@dataclass
class Arena:
    cages: dict[str, Cage]
    tunnels: dict[str, Tunnel]
    antennas: dict[int, Antenna]

    _pairs: dict[tuple[int, int], Cage | Crossing] = field(default_factory=dict)

    def classify(self, a_from: int, a_to: int) -> Cage | Crossing | None:
        """Resolve an ordered antenna pair to a dwelling (Cage) or Crossing."""
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
            assert a.adjacent_cage_id in self.cages, f"antenna {a.id} bad cage"

    def to_dimension_frames(self) -> dict:
        import polars as pl
        cages = pl.DataFrame([{"cage_id": c.id, "cage_no": c.cage_no,
                               "cell_id": c.cell_id, "cage_type": c.cage_type}
                              for c in self.cages.values()]).sort("cage_no")
        antennas = pl.DataFrame([{"antenna_id": a.id, "tunnel_id": a.tunnel_id,
                                  "tunnel_side": a.side,
                                  "adjacent_cage_id": a.adjacent_cage_id}
                                 for a in self.antennas.values()]).sort("antenna_id")
        return {"cages": cages, "antennas": antennas}

    @classmethod
    def from_json(cls, cfg: dict, interpolate: bool = False) -> "Arena":
        layout = cfg["layout"]
        cages = {cid: Cage(id=cid, cage_no=int(c["cage_no"]),
                           cell_id=c["cell_id"], cage_type=c["cage_type"])
                 for cid, c in layout["cages"].items()}
        cell_to_cage = {c.cell_id: c.id for c in cages.values()}

        tunnels, antennas = {}, {}
        for tid, t in layout["tunnels"].items():
            a_start, a_end = (int(x) for x in t["antennas"])
            cage_start = cell_to_cage[t["start_cell_id"]]
            cage_end = cell_to_cage[t["end_cell_id"]]
            tunnels[tid] = Tunnel(id=tid, name=t["name"],
                                  endpoints=frozenset({cage_start, cage_end}),
                                  antennas={cage_start: a_start, cage_end: a_end})
            antennas[a_start] = Antenna(a_start, tid, cage_start, "start")
            antennas[a_end] = Antenna(a_end, tid, cage_end, "end")

        # build the read-pair lookup from the chosen combination map
        combos = (layout["antenna_combinations_interp"] if interpolate
                  else layout["antenna_combinations"])
        tmap = layout["tunnels_map"]
        pairs: dict[tuple[int, int], Cage | Crossing] = {}
        for key, interp in combos.items():
            a, b = (int(x) for x in key.split("_"))
            if interp.startswith("cage_"):
                pairs[(a, b)] = cages[interp]
            else:                                   # e.g. "c2_c1"
                ft, tt = interp.split("_")
                pairs[(a, b)] = Crossing(tunnel_id=tmap[interp],
                                         from_cage_id=f"cage_{ft[1:]}",
                                         to_cage_id=f"cage_{tt[1:]}")
        arena = cls(cages, tunnels, antennas, pairs)
        arena.validate()
        return arena


def roster_from_v2_json(cfg: dict) -> dict[str, Animal]:
    out = {}
    animals = cfg["animals"]
    for tag, r in animals["rows"].items():
        notes = r.get("notes", "") or ""
        match animals["age_input_mode"]:
            case "age":
                age = {"age" : r.get("age")["value"], "unit" : r.get("age")["unit"]}
                dob = None
            case "dob":
                age = None
                dob = r.get("dob")
        
        out[tag] = Animal(
            tag_no=tag, sex=r.get("sex"), genotype=r.get("genotype"),
            treatment=r.get("treatment"), age = age, dob = dob,
            notes=notes,
        )

    return out



def location_kind(p: Position) -> str:
    return "cage" if isinstance(p, Cage) else "tunnel"