import json
from pathlib import Path
import datetime as dt
from .domain import Experiment, Animal, Layout, Cage, Antenna, Crossing, Tunnel


def build_layout(layout_cfg: dict, interpolate: bool = False) -> Layout:
    cages = {cid: Cage(id=cid, cage_no=int(c["cage_no"]),
                       cage_type=c["cage_type"])
             for cid, c in layout_cfg["cages"].items()}
    # cell_id is a raw-config detail used only to resolve which cage a
    # tunnel connects to; it has no place on the domain Cage object.
    cell_to_cage = {c["cell_id"]: cid for cid, c in layout_cfg["cages"].items()}

    tunnels, antennas = {}, {}
    for tid, t in layout_cfg["tunnels"].items():
        a_start, a_end = (int(x) for x in t["antennas"])
        cage_start = cell_to_cage[t["start_cell_id"]]
        cage_end = cell_to_cage[t["end_cell_id"]]
        tunnels[tid] = Tunnel(id=tid, name=t["name"],
                              endpoints=frozenset({cage_start, cage_end}),
                              antennas={cage_start: a_start, cage_end: a_end})
        antennas[a_start] = Antenna(a_start, tid, cage_start)
        antennas[a_end] = Antenna(a_end, tid, cage_end)

    combos = (layout_cfg["antenna_combinations_interp"] if interpolate
              else layout_cfg["antenna_combinations"])
    tmap = layout_cfg["tunnels_map"]
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

    layout = Layout(cages, tunnels, antennas, pairs)
    layout.validate()
    return layout


class JsonConfigLoader:

    def __init__(self, path: Path):
        self._cfg = json.loads(Path(path).read_text())

    @property
    def layout_cfg(self) -> dict:
        return self._cfg["layout"]

    def load_layout(self, interpolate: bool = False) -> Layout:
        return build_layout(self.layout_cfg, interpolate)

    def load_animals(self) -> dict[str, Animal]:
        out = {}
        animals = self._cfg["animals"]
        for tag, r in animals["rows"].items():
            notes = r.get("notes", "") or ""
            out[tag] = Animal(
                tag_no=tag, sex=r.get("sex"), genotype=r.get("genotype"),
                treatment=r.get("treatment"), age=r.get("age"),
                notes=notes,
            )
        return out
    
    def load_experiment(self, interpolate: bool = False) -> Experiment:
        meta = self._cfg["experiment"]
        env = self._cfg["environment"]
        end = meta.get("end")
        return Experiment(
            name=meta["name"],
            start=dt.datetime.fromisoformat(meta["start_datetime"]),
            end=dt.datetime.fromisoformat(end) if end else None,
            recording_timezone=meta["recording_timezone"],
            light_start=env["light_start_hhmm"],
            dark_start=env["light_end_hhmm"],  # dark phase begins when the light phase ends
            animals=self.load_animals(),
            layout=self.load_layout(interpolate),
        )