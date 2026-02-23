"""Generador de fixture con restricciones de localía (round-robin + CP-SAT)."""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from itertools import combinations

try:
    from ortools.sat.python import cp_model
except ModuleNotFoundError:
    cp_model = None

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EQUIPOS_JSON = os.path.join(SCRIPT_DIR, "equipos.json")
OUTPUT_JSON = os.path.join(SCRIPT_DIR, "fixture_output.json")
NUM_FECHAS = 26

INF_CATS = ["quinta", "sexta", "septima", "octava", "novena", "decima", "undecima"]
FEM_CATS = ["femenino_primera", "femenino_sub16", "femenino_sub14", "femenino_sub12"]

COMP_DEFS = [
    ("PRIMERA_A", ["primera"], "A"),
    ("PRIMERA_B", ["primera"], "B"),
    ("INF_A", INF_CATS, "A"),
    ("INF_B", INF_CATS, "B"),
    ("INF_C", INF_CATS, "C"),
    ("FEMENINO", FEM_CATS, None),
]


def tiene_cat(equipo: dict, cat: str) -> bool:
    return equipo.get("categorias", {}).get(cat, False) is True


def round_robin_rounds(teams: list[str]) -> list[list[tuple[str, str]]]:
    """Algoritmo canónico de rotación para todos contra todos (1 vuelta)."""
    pool = list(teams)
    if len(pool) % 2 == 1:
        pool.append("BYE")

    n = len(pool)
    fixed = pool[0]
    rotating = pool[1:]
    rounds: list[list[tuple[str, str]]] = []

    for _ in range(n - 1):
        circle = [fixed] + rotating
        pairs = []
        for i in range(n // 2):
            a = circle[i]
            b = circle[n - 1 - i]
            if a != "BYE" and b != "BYE":
                pairs.append((a, b))
        rounds.append(pairs)
        rotating = [rotating[-1]] + rotating[:-1]

    return rounds


def build_competitions(equipos_data: list[dict]) -> dict[str, dict[str, list[str]]]:
    competitions: dict[str, dict[str, list[str]]] = {}
    for ck, cats, division in COMP_DEFS:
        entities = sorted(
            {
                e["nombre"]
                for e in equipos_data
                if any(tiene_cat(e, c) for c in cats)
                and (division is None or e.get("divisionMayor") == division)
            }
        )
        if len(entities) >= 2:
            competitions[ck] = {"entities": entities}
    return competitions


def main() -> int:
    if cp_model is None:
        print("❌ Falta dependencia: ortools. Instalar con `python -m pip install ortools`.")
        return 1

    if not os.path.exists(EQUIPOS_JSON):
        print(f"❌ No existe {EQUIPOS_JSON}")
        return 1

    with open(EQUIPOS_JSON, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    equipos_data: list[dict] = data["equipos"]
    estadio_de = {e["nombre"]: e.get("estadioLocal", "A confirmar") for e in equipos_data}
    competitions = build_competitions(equipos_data)
    all_entities = sorted({t for c in competitions.values() for t in c["entities"]})

    print("=== COMPETENCIAS ===")
    for ck, comp in competitions.items():
        n = len(comp["entities"])
        print(f"  {ck:12s}: {n:2d} equipos · {(n - 1) * 2:2d} rondas")

    all_games: list[tuple[int, str, str, str]] = []
    for ck, comp in competitions.items():
        rounds = round_robin_rounds(comp["entities"])
        nr = len(rounds)
        for r, matches in enumerate(rounds, start=1):
            for a, b in matches:
                all_games.append((r, ck, a, b))
        for r, matches in enumerate(rounds, start=1):
            for a, b in matches:
                all_games.append((nr + r, ck, a, b))

    total_games = len(all_games)
    print(f"\nFase 1 completada: {total_games} partidos con fecha fija")

    games_by_date_team: defaultdict[tuple[int, str], list[int]] = defaultdict(list)
    games_by_date_comp: defaultdict[tuple[int, str], list[int]] = defaultdict(list)

    for idx, (fecha, ck, a, b) in enumerate(all_games):
        games_by_date_team[(fecha, a)].append(idx)
        games_by_date_team[(fecha, b)].append(idx)
        games_by_date_comp[(fecha, ck)].append(idx)

    model = cp_model.CpModel()
    local = [model.NewBoolVar(f"loc_{i}") for i in range(total_games)]

    def is_local(game_idx: int, team: str):
        _, _, a, b = all_games[game_idx]
        if team == a:
            return local[game_idx]
        if team == b:
            return local[game_idx].Not()
        raise ValueError(f"{team} no juega partido {game_idx}")

    def is_away(game_idx: int, team: str):
        _, _, a, b = all_games[game_idx]
        if team == a:
            return local[game_idx].Not()
        if team == b:
            return local[game_idx]
        raise ValueError(f"{team} no juega partido {game_idx}")

    def vars_team_global(fecha: int, team: str, home: bool):
        f = is_local if home else is_away
        return [f(g, team) for g in games_by_date_team[(fecha, team)]]

    def vars_team_comp(fecha: int, ck: str, team: str, home: bool):
        f = is_local if home else is_away
        return [
            f(g, team)
            for g in games_by_date_comp[(fecha, ck)]
            if team in (all_games[g][2], all_games[g][3])
        ]

    def co_local(ck_a: str, a: str, b: str):
        if a not in all_entities or b not in all_entities:
            return
        if a not in competitions.get(ck_a, {}).get("entities", []):
            return
        for fecha in range(1, NUM_FECHAS + 1):
            h_a = vars_team_comp(fecha, ck_a, a, home=True)
            v_a = vars_team_comp(fecha, ck_a, a, home=False)
            h_b = vars_team_global(fecha, b, home=True)
            v_b = vars_team_global(fecha, b, home=False)
            for xa in h_a:
                for yb in v_b:
                    model.Add(xa + yb <= 1)
            for xa in v_a:
                for yb in h_b:
                    model.Add(xa + yb <= 1)

    def cross(ck_a: str, a: str, ck_b: str | None, b: str):
        if a not in all_entities or b not in all_entities:
            return
        if a not in competitions.get(ck_a, {}).get("entities", []):
            return
        for fecha in range(1, NUM_FECHAS + 1):
            h_a = vars_team_comp(fecha, ck_a, a, home=True)
            v_a = vars_team_comp(fecha, ck_a, a, home=False)
            if ck_b and b in competitions.get(ck_b, {}).get("entities", []):
                h_b = vars_team_comp(fecha, ck_b, b, home=True)
                v_b = vars_team_comp(fecha, ck_b, b, home=False)
            else:
                h_b = vars_team_global(fecha, b, home=True)
                v_b = vars_team_global(fecha, b, home=False)
            for xa in h_a:
                for yb in h_b:
                    model.Add(xa + yb <= 1)
            for xa in v_a:
                for yb in v_b:
                    model.Add(xa + yb <= 1)

    def cross_global(a: str, b: str):
        if a not in all_entities or b not in all_entities:
            return
        for fecha in range(1, NUM_FECHAS + 1):
            h_a = vars_team_global(fecha, a, home=True)
            v_a = vars_team_global(fecha, a, home=False)
            h_b = vars_team_global(fecha, b, home=True)
            v_b = vars_team_global(fecha, b, home=False)
            for xa in h_a:
                for yb in h_b:
                    model.Add(xa + yb <= 1)
            for xa in v_a:
                for yb in v_b:
                    model.Add(xa + yb <= 1)

    print("\nAplicando restricciones de localía...")

    co_local("PRIMERA_B", "Loma Negra", "Loma Negra Inferiores")
    co_local("PRIMERA_B", "Loma Negra", "Loma Negra Femenino")

    cross("PRIMERA_A", "Independiente", None, "Independiente Femenino")
    cross("INF_B", "Independiente (rojo)", "PRIMERA_A", "Independiente")
    co_local("INF_B", "Independiente (rojo)", "Independiente Femenino")

    co_local("PRIMERA_B", "BOTAFOGO F.C.", "BOTAFOGO F.C. Inferiores")

    cross("PRIMERA_A", "Ferrocarril Sud", None, "Ferrocarril Sud Femenino")
    cross("INF_B", "Ferro Azul", "PRIMERA_A", "Ferrocarril Sud")
    co_local("INF_B", "Ferro Azul", "Ferrocarril Sud Femenino")

    co_local("PRIMERA_A", "DEFENSORES DE AYACUCHO", "DEFENSORES DE AYACUCHO Inferiores")
    co_local("PRIMERA_A", "Velense", "Velense Inferiores")
    co_local("PRIMERA_B", "Argentino", "Argentino Inferiores")

    co_local("PRIMERA_B", "San José", "San José Inferiores")
    cross("PRIMERA_B", "San José", "PRIMERA_B", "Excursionistas")
    cross_global("San José", "Excursionistas Femenino")
    co_local("PRIMERA_B", "Excursionistas", "Excursionistas Femenino")

    co_local("PRIMERA_B", "Alumni", "Alumni Inferiores")
    cross("PRIMERA_B", "Alumni", "PRIMERA_A", "Juarense")

    co_local("PRIMERA_A", "Deportivo Tandil", "Deportivo Tandil Inferiores")
    cross("PRIMERA_A", "Deportivo Tandil", None, "Juventud Unida Fem (Blanco)")
    cross("PRIMERA_A", "Deportivo Tandil", "PRIMERA_B", "Defensores del Cerro")

    co_local("PRIMERA_B", "Defensores del Cerro", "Defensores del Cerro Inferiores")
    co_local("PRIMERA_B", "Defensores del Cerro", "Juventud Unida Fem (Blanco)")

    cross("PRIMERA_A", "Juarense", None, "Juarense Femenino")

    co_local("PRIMERA_A", "UNICEN", "UNICEN")
    co_local("PRIMERA_B", "Grupo Universitario", "Grupo Universitario")
    cross("PRIMERA_A", "UNICEN", "PRIMERA_B", "Grupo Universitario")

    co_local("PRIMERA_A", "ATLETICO AYACUCHO", "ATLETICO AYACUCHO Inferiores")
    cross("PRIMERA_A", "ATLETICO AYACUCHO", None, "ATLETICO AYACUCHO Femenino")

    co_local("PRIMERA_A", "SARMIENTO (AYACUCHO)", "SARMIENTO (AYACUCHO) Inferiores")
    co_local("PRIMERA_B", "ATENEO ESTRADA", "ATENEO ESTRADA Inferiores")
    cross("PRIMERA_A", "SARMIENTO (AYACUCHO)", "PRIMERA_B", "ATENEO ESTRADA")

    co_local("PRIMERA_B", "DEPORTIVO RAUCH", "DEPORTIVO RAUCH Inferiores")

    co_local("PRIMERA_A", "Santamarina", "Santamarina")
    cross("PRIMERA_A", "Santamarina", None, "Santamarina Femenino")
    cross("PRIMERA_A", "Santamarina", "PRIMERA_B", "Oficina")
    co_local("PRIMERA_B", "Oficina", "Santamarina Femenino")

    co_local("PRIMERA_A", "Gimnasia y Esgrima", "Gimnasia y Esgrima")
    cross("PRIMERA_A", "Gimnasia y Esgrima", None, "Gimnasia y Esgrima Femenino")

    co_local("PRIMERA_A", "Juventud Unida", "Juventud Unida Infantiles")
    cross("PRIMERA_A", "Juventud Unida", "PRIMERA_B", "Unión y Progreso")
    co_local("PRIMERA_A", "Juventud Unida", "San José Femenino")
    co_local("PRIMERA_A", "Juventud Unida", "Juventud Unida Fem (Negro)")
    cross("PRIMERA_B", "Unión y Progreso", None, "San José Femenino")
    cross("PRIMERA_B", "Unión y Progreso", None, "Juventud Unida Fem (Negro)")

    co_local("PRIMERA_B", "SAN LORENZO (RAUCH)", "SAN LORENZO (RAUCH) Inferiores")
    co_local("PRIMERA_B", "SAN LORENZO (RAUCH)", "SAN LORENZO (RAUCH) Femenino")

    # Regla general: clubes que comparten estadio se cruzan, salvo excepciones explícitas.
    exceptions = {
        frozenset(("Loma Negra", "Loma Negra Inferiores")),
        frozenset(("Loma Negra", "Loma Negra Femenino")),
        frozenset(("Independiente (rojo)", "Independiente Femenino")),
        frozenset(("BOTAFOGO F.C.", "BOTAFOGO F.C. Inferiores")),
        frozenset(("Ferro Azul", "Ferrocarril Sud Femenino")),
        frozenset(("DEFENSORES DE AYACUCHO", "DEFENSORES DE AYACUCHO Inferiores")),
        frozenset(("Velense", "Velense Inferiores")),
        frozenset(("Argentino", "Argentino Inferiores")),
        frozenset(("San José", "San José Inferiores")),
        frozenset(("Excursionistas", "Excursionistas Femenino")),
        frozenset(("Alumni", "Alumni Inferiores")),
        frozenset(("Deportivo Tandil", "Deportivo Tandil Inferiores")),
        frozenset(("Defensores del Cerro", "Defensores del Cerro Inferiores")),
        frozenset(("Defensores del Cerro", "Juventud Unida Fem (Blanco)")),
        frozenset(("ATLETICO AYACUCHO", "ATLETICO AYACUCHO Inferiores")),
        frozenset(("SARMIENTO (AYACUCHO)", "SARMIENTO (AYACUCHO) Inferiores")),
        frozenset(("ATENEO ESTRADA", "ATENEO ESTRADA Inferiores")),
        frozenset(("DEPORTIVO RAUCH", "DEPORTIVO RAUCH Inferiores")),
        frozenset(("Oficina", "Santamarina Femenino")),
        frozenset(("Juventud Unida", "Juventud Unida Fem (Negro)")),
        frozenset(("SAN LORENZO (RAUCH)", "SAN LORENZO (RAUCH) Inferiores")),
        frozenset(("SAN LORENZO (RAUCH)", "SAN LORENZO (RAUCH) Femenino")),
    }

    estadio_grupos: defaultdict[str, list[str]] = defaultdict(list)
    for team, stadium in estadio_de.items():
        estadio_grupos[stadium].append(team)

    for teams in estadio_grupos.values():
        if len(teams) < 2:
            continue
        for a, b in combinations(sorted(set(teams)), 2):
            if frozenset((a, b)) not in exceptions:
                cross_global(a, b)

    # Ayacucho: máximo 2 locales simultáneos.
    ayacucho_teams = [
        t
        for t in ["DEFENSORES DE AYACUCHO", "ATLETICO AYACUCHO", "SARMIENTO (AYACUCHO)", "ATENEO ESTRADA"]
        if t in all_entities
    ]
    for fecha in range(1, NUM_FECHAS + 1):
        vars_home = [v for t in ayacucho_teams for v in vars_team_global(fecha, t, home=True)]
        if len(vars_home) >= 3:
            model.Add(sum(vars_home) <= 2)

    # Alternancia: no 4 locales ni 4 visitas en ventanas de 4.
    penalties = []
    run3_flags = {}

    for team in all_entities:
        home_f = {}
        away_f = {}
        team_penalties = []

        for fecha in range(1, NUM_FECHAS + 1):
            hv = vars_team_global(fecha, team, home=True)
            av = vars_team_global(fecha, team, home=False)
            home_f[fecha] = hv[0] if len(hv) == 1 else (sum(hv) if hv else 0)
            away_f[fecha] = av[0] if len(av) == 1 else (sum(av) if av else 0)

        for d in range(1, NUM_FECHAS - 2):
            w_home = [home_f[d + k] for k in range(4)]
            w_away = [away_f[d + k] for k in range(4)]
            if any(not isinstance(x, int) for x in w_home):
                model.Add(sum(w_home) <= 3)
            if any(not isinstance(x, int) for x in w_away):
                model.Add(sum(w_away) <= 3)

        for d in range(1, NUM_FECHAS - 1):
            w3h = [home_f[d + k] for k in range(3)]
            if any(not isinstance(x, int) for x in w3h):
                ph = model.NewBoolVar(f"p3h_{team}_{d}")
                model.Add(sum(w3h) == 3).OnlyEnforceIf(ph)
                model.Add(sum(w3h) <= 2).OnlyEnforceIf(ph.Not())
                team_penalties.append(ph)
                penalties.append(ph)

            w3a = [away_f[d + k] for k in range(3)]
            if any(not isinstance(x, int) for x in w3a):
                pa = model.NewBoolVar(f"p3a_{team}_{d}")
                model.Add(sum(w3a) == 3).OnlyEnforceIf(pa)
                model.Add(sum(w3a) <= 2).OnlyEnforceIf(pa.Not())
                team_penalties.append(pa)
                penalties.append(pa)

        run3 = model.NewBoolVar(f"run3_{team}")
        if team_penalties:
            model.AddMaxEquality(run3, team_penalties)
        else:
            model.Add(run3 == 0)
        run3_flags[team] = run3

    if run3_flags:
        model.AddMinEquality(model.NewIntVar(0, 1, "run3_min"), list(run3_flags.values()))
        model.AddMaxEquality(model.NewIntVar(0, 1, "run3_max"), list(run3_flags.values()))
        run_vals = list(run3_flags.values())
        for i in range(1, len(run_vals)):
            model.Add(run_vals[i] == run_vals[0])

    model.Minimize(sum(penalties) if penalties else 0)

    print(f"\n🔄 Resolviendo: {total_games} vars de localía")
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 300.0
    solver.parameters.num_search_workers = 8

    status = solver.Solve(model)
    status_txt = {
        cp_model.OPTIMAL: "✅ ÓPTIMO",
        cp_model.FEASIBLE: "⚡ FACTIBLE",
        cp_model.INFEASIBLE: "❌ INFACTIBLE",
        cp_model.UNKNOWN: "❓ DESCONOCIDO",
    }
    print(f"Estado: {status_txt.get(status, status)}")

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return 1

    fixture = []
    for i, (fecha, ck, a, b) in enumerate(all_games):
        home, away = (a, b) if solver.Value(local[i]) else (b, a)
        fixture.append(
            {
                "competencia": ck,
                "fecha": fecha,
                "local": home,
                "visitante": away,
                "estadio": estadio_de.get(home, "A confirmar"),
            }
        )

    fixture.sort(key=lambda x: (x["competencia"], x["fecha"], x["local"]))
    with open(OUTPUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(fixture, fh, indent=2, ensure_ascii=False)

    print(f"✅ Fixture generado: {len(fixture)} partidos en {OUTPUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
