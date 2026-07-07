import json
from dataclasses import dataclass
from pathlib import Path
import datetime as dt
from domain import Experiment, Animal, Arena, Cage, Antenna, Crossing, Tunnel


class JsonConfigLoader:

    def __init__(self, path: Path):
        self._cfg = json.loads(Path(path).read_text())

    def load_arena(self, interpolate: bool = False) -> Arena:
        layout = self._cfg["layout"]

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

        combos = (layout["antenna_combinations_interp"] if interpolate
                  else layout["antenna_combinations"])
        tmap = layout["tunnels_map"]
        pairs: dict[tuple[int, int], Cage | Crossing] = {}
        for key, interp in combos.items():
            a, b = (int(x) for x in key.split("_"))
            if interp.startswith("cage_"):
                pairs[(a, b)] = cages[interp]
            else:                                   
                ft, tt = interp.split("_")
                pairs[(a, b)] = Crossing(tunnel_id=tmap[interp],
                                         from_cage_id=f"cage_{ft[1:]}",
                                         to_cage_id=f"cage_{tt[1:]}")

        arena = Arena(cages, tunnels, antennas, pairs)
        arena.validate()   
        return arena

    def load_animals(self) -> dict[str, Animal]:
        out = {}
        animals = self._cfg["animals"]
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
    
    def load_experiment(self, interpolate: bool = False) -> Experiment:
        meta = self._cfg["experiment"]          
        env = self._cfg["environment"]
        return Experiment(
            name=meta["name"],
            start=dt.datetime.fromisoformat(meta["start"]),
            end=dt.datetime.fromisoformat(meta["end"]),
            recording_timezone=meta["recording_timezone"],
            light_start=env["light_start_hhmm"],
            dark_start=env["light_start_hhmm"],
            animals=self.load_animals(),
            layout=self.load_arena(interpolate),
        )