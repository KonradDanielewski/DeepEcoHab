import psycopg

from .domain import Experiment, Animal, Layout, Cage, Tunnel, Antenna, Crossing


SCHEMA = """
    CREATE SEQUENCE IF NOT EXISTS seq_project_id START 1;
    CREATE TABLE IF NOT EXISTS project (
        project_id         INTEGER PRIMARY KEY DEFAULT nextval('seq_project_id'),
        name                VARCHAR NOT NULL UNIQUE
    );
    CREATE SEQUENCE IF NOT EXISTS seq_experiment_id START 1;
    CREATE TABLE IF NOT EXISTS experiment (
        experiment_id       INTEGER PRIMARY KEY DEFAULT nextval('seq_experiment_id'),
        name                 VARCHAR NOT NULL UNIQUE,
        start_ts             TIMESTAMPTZ,
        end_ts                TIMESTAMPTZ,
        light_start           VARCHAR,
        dark_start            VARCHAR,
        recording_timezone    VARCHAR,
        layout_interpolated   BOOLEAN NOT NULL
    );
    CREATE SEQUENCE IF NOT EXISTS seq_animal_id START 1;
    CREATE TABLE IF NOT EXISTS animal (
        animal_id          INTEGER PRIMARY KEY DEFAULT nextval('seq_animal_id'),
        experiment_id      INTEGER NOT NULL REFERENCES experiment(experiment_id),
        tag_no             VARCHAR NOT NULL,
        sex                VARCHAR,
        genotype           VARCHAR,
        treatment          VARCHAR,
        genetic_background VARCHAR,
        mouse_line         VARCHAR,
        age                VARCHAR,
        notes              VARCHAR,
        UNIQUE (experiment_id, tag_no)
    );
    CREATE SEQUENCE IF NOT EXISTS seq_cage_pk START 1;
    CREATE TABLE IF NOT EXISTS cage (
        cage_pk        INTEGER PRIMARY KEY DEFAULT nextval('seq_cage_pk'),
        experiment_id  INTEGER NOT NULL REFERENCES experiment(experiment_id),
        cage_id        VARCHAR NOT NULL,
        cage_no        INTEGER NOT NULL,
        cage_type      VARCHAR,
        UNIQUE (experiment_id, cage_id)
    );
    CREATE SEQUENCE IF NOT EXISTS seq_tunnel_pk START 1;
    CREATE TABLE IF NOT EXISTS tunnel (
        tunnel_pk      INTEGER PRIMARY KEY DEFAULT nextval('seq_tunnel_pk'),
        experiment_id  INTEGER NOT NULL REFERENCES experiment(experiment_id),
        tunnel_id      VARCHAR NOT NULL,
        name           VARCHAR,
        cage_a_id      VARCHAR NOT NULL,
        cage_b_id      VARCHAR NOT NULL,
        is_deadend     BOOLEAN NOT NULL DEFAULT FALSE,
        UNIQUE (experiment_id, tunnel_id),
        FOREIGN KEY (experiment_id, cage_a_id) REFERENCES cage(experiment_id, cage_id),
        FOREIGN KEY (experiment_id, cage_b_id) REFERENCES cage(experiment_id, cage_id)
    );
    CREATE TABLE IF NOT EXISTS antenna (
        experiment_id  INTEGER NOT NULL REFERENCES experiment(experiment_id),
        antenna_id     INTEGER NOT NULL,
        tunnel_id      VARCHAR NOT NULL,
        cage_id        VARCHAR NOT NULL,
        PRIMARY KEY (experiment_id, antenna_id),
        FOREIGN KEY (experiment_id, tunnel_id) REFERENCES tunnel(experiment_id, tunnel_id),
        FOREIGN KEY (experiment_id, cage_id) REFERENCES cage(experiment_id, cage_id)
    );
    CREATE TABLE IF NOT EXISTS antenna_pair (
        experiment_id  INTEGER NOT NULL REFERENCES experiment(experiment_id),
        antenna_from   INTEGER NOT NULL,
        antenna_to     INTEGER NOT NULL,
        kind           VARCHAR NOT NULL,
        cage_id        VARCHAR,
        tunnel_id      VARCHAR,
        from_cage_id   VARCHAR,
        to_cage_id     VARCHAR,
        PRIMARY KEY (experiment_id, antenna_from, antenna_to),
        FOREIGN KEY (experiment_id, antenna_from) REFERENCES antenna(experiment_id, antenna_id),
        FOREIGN KEY (experiment_id, antenna_to) REFERENCES antenna(experiment_id, antenna_id)
    );
"""

def connect(dsn: str) -> psycopg.Connection:
    con = psycopg.connect(dsn, autocommit=True)
    con.execute(SCHEMA)
    return con

class PostgresExperimentRepository:
    def __init__(self, con: psycopg.Connection):
        self._con = con

    def exists(self, name: str) -> bool:
        return self._con.execute(
            "SELECT 1 FROM experiment WHERE name = %s", [name]
        ).fetchone() is not None

    def save(self, exp: Experiment, interpolate: bool) -> None:
        with self._con.transaction():
            exp_id = self._con.execute(
                """INSERT INTO experiment
                   (name, start_ts, end_ts, light_start, dark_start,
                    recording_timezone, layout_interpolated)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   RETURNING experiment_id""",
                [exp.name, exp.start, exp.end, exp.light_start,
                 exp.dark_start, exp.recording_timezone, interpolate],
            ).fetchone()[0]

            if exp.animals:
                self._con.cursor().executemany(
                    """INSERT INTO animal
                       (experiment_id, tag_no, sex, genotype, treatment,
                        genetic_background, mouse_line, age, notes)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    [
                        (exp_id, a.tag_no, a.sex, a.genotype, a.treatment,
                         a.genetic_background, a.mouse_line, a.age, a.notes)
                        for a in exp.animals.values()
                    ],
                )

            layout = exp.layout

            if layout.cages:
                self._con.cursor().executemany(
                    """INSERT INTO cage (experiment_id, cage_id, cage_no, cage_type)
                       VALUES (%s, %s, %s, %s)""",
                    [(exp_id, c.id, c.cage_no, c.cage_type) for c in layout.cages.values()],
                )

            if layout.tunnels:
                tunnel_rows = []
                for t in layout.tunnels.values():
                    # antennas dict preserves the start/end insertion order set by build_layout
                    cage_a_id, cage_b_id = t.antennas.keys()
                    tunnel_rows.append((exp_id, t.id, t.name, cage_a_id, cage_b_id, t.is_deadend))
                self._con.cursor().executemany(
                    """INSERT INTO tunnel
                       (experiment_id, tunnel_id, name, cage_a_id, cage_b_id, is_deadend)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    tunnel_rows,
                )

            if layout.antennas:
                self._con.cursor().executemany(
                    """INSERT INTO antenna (experiment_id, antenna_id, tunnel_id, cage_id)
                       VALUES (%s, %s, %s, %s)""",
                    [(exp_id, a.id, a.tunnel_id, a.cage_id) for a in layout.antennas.values()],
                )

            if layout.pairs:
                pair_rows = []
                for (a_from, a_to), target in layout.pairs.items():
                    if isinstance(target, Cage):
                        pair_rows.append(
                            (exp_id, a_from, a_to, "cage", target.id, None, None, None)
                        )
                    else:
                        pair_rows.append((
                            exp_id, a_from, a_to, "crossing", None,
                            target.tunnel_id, target.from_cage_id, target.to_cage_id,
                        ))
                self._con.cursor().executemany(
                    """INSERT INTO antenna_pair
                       (experiment_id, antenna_from, antenna_to, kind, cage_id,
                        tunnel_id, from_cage_id, to_cage_id)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    pair_rows,
                )

    def get(self, name: str) -> Experiment | None:
        exp_row = self._con.execute(
            """SELECT experiment_id, name, start_ts, end_ts, light_start,
                      dark_start, recording_timezone
               FROM experiment WHERE name = %s""", [name]
        ).fetchone()
        if exp_row is None:
            return None
        exp_id, name, start_ts, end_ts, light_start, dark_start, tz = exp_row

        animal_rows = self._con.execute(
            """SELECT tag_no, sex, genotype, treatment, genetic_background,
                      mouse_line, age, notes
               FROM animal WHERE experiment_id = %s""", [exp_id]
        ).fetchall()
        animals = {
            r[0]: Animal(
                tag_no=r[0], sex=r[1], genotype=r[2], treatment=r[3],
                genetic_background=r[4], mouse_line=r[5], age=r[6], notes=r[7] or "",
            )
            for r in animal_rows
        }

        cage_rows = self._con.execute(
            "SELECT cage_id, cage_no, cage_type FROM cage WHERE experiment_id = %s", [exp_id]
        ).fetchall()
        cages = {r[0]: Cage(id=r[0], cage_no=r[1], cage_type=r[2]) for r in cage_rows}

        antenna_rows = self._con.execute(
            "SELECT antenna_id, tunnel_id, cage_id FROM antenna WHERE experiment_id = %s", [exp_id]
        ).fetchall()
        antennas = {r[0]: Antenna(id=r[0], tunnel_id=r[1], cage_id=r[2]) for r in antenna_rows}

        tunnel_antennas: dict[str, dict[str, int]] = {}
        for a in antennas.values():
            tunnel_antennas.setdefault(a.tunnel_id, {})[a.cage_id] = a.id

        tunnel_rows = self._con.execute(
            """SELECT tunnel_id, name, cage_a_id, cage_b_id, is_deadend
               FROM tunnel WHERE experiment_id = %s""", [exp_id]
        ).fetchall()
        tunnels = {
            r[0]: Tunnel(
                id=r[0], name=r[1], endpoints=frozenset({r[2], r[3]}),
                antennas=tunnel_antennas.get(r[0], {}), is_deadend=r[4],
            )
            for r in tunnel_rows
        }

        pair_rows = self._con.execute(
            """SELECT antenna_from, antenna_to, kind, cage_id, tunnel_id,
                      from_cage_id, to_cage_id
               FROM antenna_pair WHERE experiment_id = %s""", [exp_id]
        ).fetchall()
        pairs: dict[tuple[int, int], Cage | Crossing] = {}
        for a_from, a_to, kind, cage_id, tunnel_id, from_cage_id, to_cage_id in pair_rows:
            if kind == "cage":
                pairs[(a_from, a_to)] = cages[cage_id]
            else:
                pairs[(a_from, a_to)] = Crossing(
                    tunnel_id=tunnel_id, from_cage_id=from_cage_id, to_cage_id=to_cage_id
                )

        layout = Layout(cages, tunnels, antennas, pairs)
        layout.validate()

        return Experiment(
            name=name, start=start_ts, end=end_ts,
            light_start=light_start, dark_start=dark_start,
            recording_timezone=tz, animals=animals, layout=layout,
        )
