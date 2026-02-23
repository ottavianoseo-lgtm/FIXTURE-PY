"""
fixture_generator.py  ·  v8.0 — MODELO DE DOS FASES
=====================================================

POR QUÉ LOS MODELOS ANTERIORES ERAN LENTOS
--------------------------------------------
v5-v7 tenían ~18,000 variables: una por cada combinación (fecha × partido).
El solver intentaba decidir SIMULTÁNEAMENTE en qué fecha va cada partido
Y quién juega de local. El espacio de búsqueda era imposible de recorrer.

SOLUCIÓN: DOS FASES
--------------------
FASE 1 (Python puro, instantánea):
  Asignar cada partido a una fecha usando el algoritmo canónico de round-robin.
  Con n equipos: ronda r = fecha r (vuelta 1), fecha n-1+r (vuelta 2).
  Resultado: 706 partidos con fecha fija.

FASE 2 (CP-SAT, solo 706 variables):
  Para cada partido ya asignado, decidir la LOCALÍA:
    local[p] = 1  →  equipo A es local
    local[p] = 0  →  equipo B es local
  El solver solo necesita satisfacer las restricciones de cruce/co-local
  sobre estos 706 bits binarios. El modelo es 26x más pequeño.
"""

import json, os, sys
from itertools import combinations
from ortools.sat.python import cp_model

# ══════════════════════════════════════════════════════════════════════════════
# 1. DATOS
# ══════════════════════════════════════════════════════════════════════════════
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
EQUIPOS_JSON = os.path.join(SCRIPT_DIR, "equipos.json")

try:
    with open(EQUIPOS_JSON, "r", encoding="utf-8") as fh:
        data = json.load(fh)
except FileNotFoundError:
    sys.exit(f"❌ No se encontró '{EQUIPOS_JSON}'.")

equipos_data = data["equipos"]
estadio_de   = {e["nombre"]: e.get("estadioLocal", "A confirmar") for e in equipos_data}

def tiene_cat(e, cat):
    return e.get("categorias", {}).get(cat, False) is True

# ══════════════════════════════════════════════════════════════════════════════
# 2. COMPETENCIAS
# ══════════════════════════════════════════════════════════════════════════════
INF_CATS = ["quinta","sexta","septima","octava","novena","decima","undecima"]
FEM_CATS = ["femenino_primera","femenino_sub16","femenino_sub14","femenino_sub12"]

COMP_DEFS = [
    ("PRIMERA_A", ["primera"], "A"),
    ("PRIMERA_B", ["primera"], "B"),
    ("INF_A",     INF_CATS,    "A"),
    ("INF_B",     INF_CATS,    "B"),
    ("INF_C",     INF_CATS,    "C"),
    ("FEMENINO",  FEM_CATS,    None),
]

COMPETITIONS = {}
for ck, cats, div in COMP_DEFS:
    parts = sorted({
        e["nombre"] for e in equipos_data
        if any(tiene_cat(e, c) for c in cats)
        and (div is None or e.get("divisionMayor") == div)
    })
    if len(parts) >= 2:
        COMPETITIONS[ck] = {"entities": parts}

NUM_FECHAS = 26
all_entities = sorted({n for c in COMPETITIONS.values() for n in c["entities"]})

print("=== COMPETENCIAS ===")
for ck, comp in COMPETITIONS.items():
    n = len(comp["entities"])
    print(f"  {ck:12s}: {n:2d} equipos · {n-1:2d} locales/equipo · {(n-1)*2:2d} rondas")

# ══════════════════════════════════════════════════════════════════════════════
# 3. FASE 1 — ASIGNACIÓN DE FECHAS (round-robin canónico)
# ══════════════════════════════════════════════════════════════════════════════

def round_robin_rounds(teams):
    """Algoritmo de rotación. Retorna lista de rondas [(t1,t2), ...]."""
    t = list(teams)
    if len(t) % 2 == 1:
        t.append("BYE")
    n = len(t)
    fixed, rotating = t[0], t[1:]
    rounds = []
    for _ in range(n - 1):
        circle = [fixed] + rotating
        pairs = [(circle[i], circle[n-1-i])
                 for i in range(n//2)
                 if circle[i] != "BYE" and circle[n-1-i] != "BYE"]
        rounds.append(pairs)
        rotating = [rotating[-1]] + rotating[:-1]
    return rounds

# Generar todos los partidos con fecha asignada
# all_games[p] = (fecha, ck, A, B)  — solver decide si A o B es local
all_games = []

for ck, comp in COMPETITIONS.items():
    rounds = round_robin_rounds(comp["entities"])
    nr = len(rounds)
    # Vuelta 1: fechas 1..nr
    for r, ronda in enumerate(rounds):
        for t1, t2 in ronda:
            all_games.append((r + 1, ck, t1, t2))
    # Vuelta 2: fechas nr+1..2*nr
    for r, ronda in enumerate(rounds):
        for t1, t2 in ronda:
            all_games.append((nr + r + 1, ck, t1, t2))

P = len(all_games)
print(f"\nFase 1 completada: {P} partidos con fechas fijas")

# Índices de partidos por (fecha, equipo) para lookup rápido
from collections import defaultdict
games_by_date_team = defaultdict(list)  # (fecha, equipo) -> [idx_partido]
games_by_date_comp = defaultdict(list)  # (fecha, ck) -> [idx_partido]

for idx, (fecha, ck, A, B) in enumerate(all_games):
    games_by_date_team[(fecha, A)].append(idx)
    games_by_date_team[(fecha, B)].append(idx)
    games_by_date_comp[(fecha, ck)].append(idx)

# ══════════════════════════════════════════════════════════════════════════════
# 4. FASE 2 — MODELO CP-SAT: solo localía
# ══════════════════════════════════════════════════════════════════════════════
model = cp_model.CpModel()

# local[p] = 1 → all_games[p][2] (equipo A) es local
# local[p] = 0 → all_games[p][3] (equipo B) es local
local = [model.NewBoolVar(f"loc_{p}") for p in range(P)]

def is_local(p, team):
    """Expresión lineal: 1 si team es local en partido p."""
    _, _, A, B = all_games[p]
    if team == A: return local[p]
    if team == B: return local[p].Not()
    raise ValueError(f"{team} no juega en partido {p}")

def is_visitor(p, team):
    _, _, A, B = all_games[p]
    if team == A: return local[p].Not()
    if team == B: return local[p]
    raise ValueError(f"{team} no juega en partido {p}")

def home_vars(fecha, ck, team):
    """Lista de vars 'team es local' en (fecha, ck)."""
    return [is_local(p, team)
            for p in games_by_date_comp[(fecha, ck)]
            if all_games[p][2] == team or all_games[p][3] == team]

def away_vars(fecha, ck, team):
    return [is_visitor(p, team)
            for p in games_by_date_comp[(fecha, ck)]
            if all_games[p][2] == team or all_games[p][3] == team]

def home_vars_global(fecha, team):
    """Lista de vars 'team es local' en cualquier comp en fecha dada."""
    return [is_local(p, team) for p in games_by_date_team[(fecha, team)]]

def away_vars_global(fecha, team):
    return [is_visitor(p, team) for p in games_by_date_team[(fecha, team)]]

# ── Restricción base: no puede ser local Y visitante el mismo día ─────────────
# (Ya está implícito porque cada equipo juega máx 1 partido/fecha/comp,
#  pero un equipo en 2 comps podría jugar 2 partidos el mismo día en comps distintas.
#  Eso está OK, pero no puede ser local en una y visitante en la otra si hay
#  restricción de co_local. La base es: un equipo puede tener max 1 partido/fecha
#  POR COMPETENCIA. Entre competencias distintas pueden coincidir.)

# ── Rachas: helper ────────────────────────────────────────────────────────────
# Para rachas necesitamos saber si el equipo tiene partido en esa fecha
def has_game(fecha, team):
    return len(games_by_date_team[(fecha, team)]) > 0

# ══════════════════════════════════════════════════════════════════════════════
# 5. RESTRICCIONES DE LOCALÍA
# ══════════════════════════════════════════════════════════════════════════════

# ── Helpers para restricciones cruzadas ──────────────────────────────────────

def co_local(ck_A, A, B):
    """
    Cuando A es local en ck_A → B no puede ser visitante (en ninguna comp).
    Bidireccional: B local (global) → A no puede ser visitante en ck_A.
    
    Formulación directa sin vars auxiliares:
      sum(home_vars(ck_A,A)) + sum(away_vars_global(B)) <= 1
      sum(home_vars_global(B)) + sum(away_vars(ck_A,A)) <= 1
    
    Nota: estos términos son al máximo 1 cada uno (un equipo juega max
    1 partido/fecha/comp), así que la constraint es entre dos vars 0/1.
    """
    if A not in all_entities or B not in all_entities: return
    if A not in COMPETITIONS.get(ck_A,{}).get("entities",[]): return

    for fecha in range(1, NUM_FECHAS+1):
        hA = home_vars(fecha, ck_A, A)
        vA = away_vars(fecha, ck_A, A)
        hB = home_vars_global(fecha, B)
        vB = away_vars_global(fecha, B)

        # Si no hay partidos ese día, no hay restricción
        if not hA and not vA: continue

        # Si A y B se enfrentan directamente ese día → H2H bypass
        is_h2h = any(
            (all_games[p][2] in (A,B) and all_games[p][3] in (A,B))
            for p in games_by_date_team[(fecha, A)]
            if p in games_by_date_team[(fecha, B)]
               # más estricto: mismo partido
        )
        # Verificación correcta de H2H
        h2h_idx = [p for p in games_by_date_team[(fecha, A)]
                   if p in games_by_date_team[(fecha, B)]
                   and {all_games[p][2], all_games[p][3]} == {A, B}]
        
        if h2h_idx:
            # Solo hay un partido directo. En ese partido no aplicamos co_local.
            # Aplicamos co_local solo en partidos de ck_A donde A NO juega vs B.
            hA_no_h2h = [v for p, v in zip(
                [pp for pp in games_by_date_comp[(fecha, ck_A)]
                 if all_games[pp][2]==A or all_games[pp][3]==A],
                hA) if p not in h2h_idx]
            # Simplificación: si el partido de A en ck_A ES el H2H, no hay restricción
            # Si el partido de A en ck_A NO es el H2H, aplicar normalmente
            for v_hA in hA_no_h2h:
                for v_vB in vB:
                    model.Add(v_hA + v_vB <= 1)
            vA_no_h2h = [v for p, v in zip(
                [pp for pp in games_by_date_comp[(fecha, ck_A)]
                 if all_games[pp][2]==A or all_games[pp][3]==A],
                vA) if p not in h2h_idx]
            for v_vA in vA_no_h2h:
                for v_hB in hB:
                    model.Add(v_vA + v_hB <= 1)
        else:
            for v_hA in hA:
                for v_vB in vB:
                    model.Add(v_hA + v_vB <= 1)
            for v_vA in vA:
                for v_hB in hB:
                    model.Add(v_vA + v_hB <= 1)


def cross(ck_A, A, ck_B_or_None, B):
    """
    Cruce: A y B siempre con condiciones OPUESTAS en sus torneos.
    A local en ck_A → B no local en ck_B (o global si ck_B=None).
    A visit en ck_A → B no visit.
    """
    if A not in all_entities or B not in all_entities: return
    if A not in COMPETITIONS.get(ck_A,{}).get("entities",[]): return

    for fecha in range(1, NUM_FECHAS+1):
        hA = home_vars(fecha, ck_A, A)
        vA = away_vars(fecha, ck_A, A)
        if ck_B_or_None and B in COMPETITIONS.get(ck_B_or_None,{}).get("entities",[]):
            hB = home_vars(fecha, ck_B_or_None, B)
            vB = away_vars(fecha, ck_B_or_None, B)
        else:
            hB = home_vars_global(fecha, B)
            vB = away_vars_global(fecha, B)

        for v_hA in hA:
            for v_hB in hB:
                model.Add(v_hA + v_hB <= 1)
        for v_vA in vA:
            for v_vB in vB:
                model.Add(v_vA + v_vB <= 1)

# ══════════════════════════════════════════════════════════════════════════════
# 6. APLICAR REGLAS
# ══════════════════════════════════════════════════════════════════════════════
print("\nAplicando restricciones de localía...")

# ── Independiente (azul, A) ────────────────────────────────────────────────────
cross("PRIMERA_A", "Independiente",       None,       "Independiente Femenino")
# ── Independiente Rojo (INF_B) ────────────────────────────────────────────────
cross("INF_B",     "Independiente (rojo)", "PRIMERA_A","Independiente")
# Rojo y Femenino van JUNTOS: cuando Azul es visitante, ambos son locales
co_local("INF_B",  "Independiente (rojo)", "Independiente Femenino")
# ── BOTAFOGO ──────────────────────────────────────────────────────────────────
co_local("PRIMERA_B", "BOTAFOGO F.C.",    "BOTAFOGO F.C. Inferiores")
# ── Ferrocarril Sud (A) ───────────────────────────────────────────────────────
cross("PRIMERA_A", "Ferrocarril Sud",     None,       "Ferrocarril Sud Femenino")
# ── Ferro Azul (INF_B) ────────────────────────────────────────────────────────
cross("INF_B",     "Ferro Azul",          "PRIMERA_A","Ferrocarril Sud")
# Azul y Femenino van JUNTOS: cuando Sud es visitante, ambos son locales
co_local("INF_B",  "Ferro Azul",           "Ferrocarril Sud Femenino")
# ── Defensores Ayacucho ───────────────────────────────────────────────────────
co_local("PRIMERA_A", "DEFENSORES DE AYACUCHO", "DEFENSORES DE AYACUCHO Inferiores")
# ── Velense ───────────────────────────────────────────────────────────────────
co_local("PRIMERA_A", "Velense",          "Velense Inferiores")
# ── Argentino ─────────────────────────────────────────────────────────────────
co_local("PRIMERA_B", "Argentino",        "Argentino Inferiores")
# ── San José ──────────────────────────────────────────────────────────────────
co_local("PRIMERA_B", "San José",         "San José Inferiores")
# San José siempre opuesto a Excursionistas masculino
cross("PRIMERA_B",    "San José",         "PRIMERA_B","Excursionistas")
# NO cross directo San José-ExcFem: triángulo imposible con Exc-ExcFem (same)
# La relación es transitiva: SJ cross Exc + Exc co_local ExcFem => SJ opp ExcFem
# ── Excursionistas ────────────────────────────────────────────────────────────
# Exc y ExcFem van JUNTOS (cuando SJ es local, Exc+ExcFem son visitantes)
co_local("PRIMERA_B", "Excursionistas",   "Excursionistas Femenino")
# ── Alumni ────────────────────────────────────────────────────────────────────
co_local("PRIMERA_B", "Alumni",           "Alumni Inferiores")
cross("PRIMERA_B",    "Alumni",           "PRIMERA_A","Juarense")
# ── Deportivo Tandil ──────────────────────────────────────────────────────────
co_local("PRIMERA_A", "Deportivo Tandil", "Deportivo Tandil Inferiores")
cross("PRIMERA_A",    "Deportivo Tandil", None,       "Juventud Unida Fem (Blanco)")
cross("PRIMERA_A",    "Deportivo Tandil", "PRIMERA_B","Defensores del Cerro")
# ── Defensores del Cerro ──────────────────────────────────────────────────────
co_local("PRIMERA_B", "Defensores del Cerro", "Defensores del Cerro Inferiores")
co_local("PRIMERA_B", "Defensores del Cerro", "Juventud Unida Fem (Blanco)")
# ── Loma Negra — EXCEPCIÓN: femenino co-local ─────────────────────────────────
co_local("PRIMERA_B", "Loma Negra",       "Loma Negra Inferiores")
co_local("PRIMERA_B", "Loma Negra",       "Loma Negra Femenino")
# ── Juarense ──────────────────────────────────────────────────────────────────
cross("PRIMERA_A",    "Juarense",         None,       "Juarense Femenino")
# ── UNICEN ────────────────────────────────────────────────────────────────────
cross("PRIMERA_A",    "UNICEN",           "PRIMERA_B","Grupo Universitario")
# ── Atlético Ayacucho ─────────────────────────────────────────────────────────
co_local("PRIMERA_A", "ATLETICO AYACUCHO","ATLETICO AYACUCHO Inferiores")
cross("PRIMERA_A",    "ATLETICO AYACUCHO",None,       "ATLETICO AYACUCHO Femenino")
# ── Sarmiento Ayacucho ────────────────────────────────────────────────────────
co_local("PRIMERA_A", "SARMIENTO (AYACUCHO)", "SARMIENTO (AYACUCHO) Inferiores")
cross("PRIMERA_A",    "SARMIENTO (AYACUCHO)","PRIMERA_B","ATENEO ESTRADA")
# ── Ateneo Estrada ────────────────────────────────────────────────────────────
co_local("PRIMERA_B", "ATENEO ESTRADA",   "ATENEO ESTRADA Inferiores")
# ── Deportivo Rauch ───────────────────────────────────────────────────────────
co_local("PRIMERA_B", "DEPORTIVO RAUCH",  "DEPORTIVO RAUCH Inferiores")
# ── Santamarina ───────────────────────────────────────────────────────────────
cross("PRIMERA_A",    "Santamarina",      None,       "Santamarina Femenino")
cross("PRIMERA_A",    "Santamarina",      "PRIMERA_B","Oficina")
# ── Gimnasia ──────────────────────────────────────────────────────────────────
cross("PRIMERA_A",    "Gimnasia y Esgrima",None,      "Gimnasia y Esgrima Femenino")
# ── Oficina ───────────────────────────────────────────────────────────────────
co_local("PRIMERA_B", "Oficina",          "Santamarina Femenino")
# ── Juventud Unida ────────────────────────────────────────────────────────────
co_local("PRIMERA_A", "Juventud Unida",   "Juventud Unida Infantiles")
cross("PRIMERA_A",    "Juventud Unida",   "PRIMERA_B","Unión y Progreso")
co_local("PRIMERA_A", "Juventud Unida",   "San José Femenino")
co_local("PRIMERA_A", "Juventud Unida",   "Juventud Unida Fem (Negro)")
# ── Unión y Progreso ──────────────────────────────────────────────────────────
cross("PRIMERA_B",    "Unión y Progreso", None,       "San José Femenino")
cross("PRIMERA_B",    "Unión y Progreso", None,       "Juventud Unida Fem (Negro)")
# ── San Lorenzo Rauch — femenino co-local (sub16, sin conflicto de cancha) ────
co_local("PRIMERA_B", "SAN LORENZO (RAUCH)", "SAN LORENZO (RAUCH) Inferiores")
co_local("PRIMERA_B", "SAN LORENZO (RAUCH)", "SAN LORENZO (RAUCH) Femenino")

# ══════════════════════════════════════════════════════════════════════════════
# 7. AYACUCHO: ≤ 2 LOCALES SIMULTÁNEOS
# ══════════════════════════════════════════════════════════════════════════════
ayacucho = [n for n in ["DEFENSORES DE AYACUCHO","ATLETICO AYACUCHO",
                         "SARMIENTO (AYACUCHO)","ATENEO ESTRADA"] if n in all_entities]

for fecha in range(1, NUM_FECHAS+1):
    aya_home = [v for n in ayacucho for v in home_vars_global(fecha, n)]
    if len(aya_home) >= 3:
        model.Add(sum(aya_home) <= 2)

# ══════════════════════════════════════════════════════════════════════════════
# 8. ALTERNANCIA: MÁXIMO 3 CONSECUTIVOS + SOFT PENALTY
# ══════════════════════════════════════════════════════════════════════════════
penalties = []

for n in all_entities:
    # Construir secuencia de condición por fecha: 1=local, -1=visit, 0=libre
    # Para rachas usamos vars booleanas por fecha
    home_f  = {}  # fecha -> var o constante
    away_f  = {}

    for fecha in range(1, NUM_FECHAS+1):
        hv = home_vars_global(fecha, n)
        av = away_vars_global(fecha, n)
        home_f[fecha] = hv[0] if len(hv) == 1 else (sum(hv) if hv else 0)
        away_f[fecha] = av[0] if len(av) == 1 else (sum(av) if av else 0)

    # Máximo 3 locales consecutivos (duro)
    for d in range(1, NUM_FECHAS - 2):
        window = [home_f[d+k] for k in range(4) if d+k <= NUM_FECHAS]
        if len(window) == 4 and any(not isinstance(w, int) for w in window):
            model.Add(sum(window) <= 3)

    # Máximo 3 visitantes consecutivos (duro)
    for d in range(1, NUM_FECHAS - 2):
        window = [away_f[d+k] for k in range(4) if d+k <= NUM_FECHAS]
        if len(window) == 4 and any(not isinstance(w, int) for w in window):
            model.Add(sum(window) <= 3)

    # Soft: penalizar ventanas de exactamente 3 locales/visitantes seguidos
    for d in range(1, NUM_FECHAS - 1):
        w3h = [home_f[d+k] for k in range(3) if d+k <= NUM_FECHAS]
        if len(w3h) == 3 and any(not isinstance(w, int) for w in w3h):
            pl = model.NewBoolVar(f"pl_{n}_{d}")
            model.Add(sum(w3h) == 3).OnlyEnforceIf(pl)
            model.Add(sum(w3h) <= 2).OnlyEnforceIf(pl.Not())
            penalties.append(pl)

        w3a = [away_f[d+k] for k in range(3) if d+k <= NUM_FECHAS]
        if len(w3a) == 3 and any(not isinstance(w, int) for w in w3a):
            pv = model.NewBoolVar(f"pv_{n}_{d}")
            model.Add(sum(w3a) == 3).OnlyEnforceIf(pv)
            model.Add(sum(w3a) <= 2).OnlyEnforceIf(pv.Not())
            penalties.append(pv)

model.Minimize(sum(penalties))

# ══════════════════════════════════════════════════════════════════════════════
# 9. RESOLUCIÓN
# ══════════════════════════════════════════════════════════════════════════════
print(f"\n🔄 Resolviendo v8 — {P} vars de localía + {len(penalties)} penalty vars")
solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 300.0
solver.parameters.num_search_workers  = 8
solver.parameters.log_search_progress = True

status = solver.Solve(model)

STATUS_TXT = {
    cp_model.OPTIMAL:    "✅ ÓPTIMO",
    cp_model.FEASIBLE:   "⚡ FACTIBLE (tiempo agotado antes del óptimo)",
    cp_model.INFEASIBLE: "❌ INFACTIBLE",
    cp_model.UNKNOWN:    "❓ DESCONOCIDO",
}
print(f"\nEstado: {STATUS_TXT.get(status, str(status))}")

if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
    fixture = []
    for p, (fecha, ck, A, B) in enumerate(all_games):
        if solver.Value(local[p]) == 1:
            loc, vis = A, B
        else:
            loc, vis = B, A
        fixture.append({
            "competencia": ck,
            "fecha":  fecha,
            "local":  loc,
            "visitante": vis,
            "estadio": estadio_de.get(loc, "A confirmar"),
        })

    fixture.sort(key=lambda x: (x["competencia"], x["fecha"], x["local"]))

    out = os.path.join(SCRIPT_DIR, "fixture_output.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(fixture, fh, indent=4, ensure_ascii=False)

    print(f"✅ {len(fixture)} partidos → {out}")
    print(f"   Penalización rachas de 3: {int(solver.ObjectiveValue())}")

    from collections import Counter, defaultdict
    cnt = Counter(p["competencia"] for p in fixture)
    print("\n=== RESUMEN ===")
    for ck in sorted(cnt):
        n   = len(COMPETITIONS[ck]["entities"])
        exp = n * (n - 1)
        print(f"  {'✓' if cnt[ck]==exp else '⚠'} {ck:12s}: {cnt[ck]:4d}/{exp:4d}")

    # Verificación femenino/masculino
    cond = defaultdict(lambda: 'libre')
    for p in fixture:
        cond[(p['fecha'], p['local'])]     = 'local'
        cond[(p['fecha'], p['visitante'])] = 'visitante'

    print("\n=== VERIFICACIÓN FEMENINO/MASCULINO ===")
    checks = [
        ("cross", "Independiente",       "Independiente Femenino"),
        ("cross", "Ferrocarril Sud",      "Ferrocarril Sud Femenino"),
        ("cross", "Excursionistas",       "Excursionistas Femenino"),
        ("cross", "Gimnasia y Esgrima",   "Gimnasia y Esgrima Femenino"),
        ("cross", "Santamarina",          "Santamarina Femenino"),
        ("cross", "Juarense",             "Juarense Femenino"),
        ("cross", "ATLETICO AYACUCHO",    "ATLETICO AYACUCHO Femenino"),
        ("coloc", "Loma Negra",           "Loma Negra Femenino"),
        ("coloc", "SAN LORENZO (RAUCH)",  "SAN LORENZO (RAUCH) Femenino"),
    ]
    for tipo, M, F in checks:
        v = sum(1 for f in range(1, NUM_FECHAS+1)
                if cond[(f,M)] != 'libre' and cond[(f,F)] != 'libre'
                and (cond[(f,M)] == cond[(f,F)] if tipo=="cross"
                     else (cond[(f,M)]=='local' and cond[(f,F)]=='visitante')))
        print(f"  {'✅' if v==0 else f'❌ {v}':<6} {tipo.upper()} {M} ↔ {F}")

elif status == cp_model.INFEASIBLE:
    print("\n❌ INFACTIBLE — hay un conflicto lógico entre restricciones.")
    print("   Ejecutar con solo el bloque 5 (sin rachas) para confirmar.")
else:
    print("\n❓ Sin solución en 300s. Probar con 600s o revisar restricciones.")
