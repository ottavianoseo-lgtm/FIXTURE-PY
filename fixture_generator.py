"""
fixture_generator.py  ·  v6.0 DEFINITIVA — REGLAS FEMENINO CORREGIDAS
==========================================

CAUSA RAÍZ DE LA INFEASIBILIDAD (RESUELTO)
--------------------------------------------
Los scripts anteriores implementaban "espejo" como es_local[A] == es_local[B],
o como co_local global usando es_local[A] = OR de TODAS las competencias de A.

Esto era imposible porque equipos como Independiente, Santamarina, Juventud Unida
etc. participan en DOS competencias (PRIMERA + INF), acumulando ~21 partidos como
local. Obligar a que su satélite (10-12 locales) estuviera local 21 veces era
matemáticamente imposible.

SOLUCIÓN DEFINITIVA: Todas las restricciones cruzadas operan sobre variables
POR COMPETENCIA ESPECÍFICA (es_local_comp, es_visitante_comp), no sobre el OR global.

Las reglas "cuando mayores es local" se refieren ÚNICAMENTE a la categoría mayor
del club (PRIMERA_A o PRIMERA_B), no a sus categorías de inferiores.

Las reglas de "cruce" entre dos clubes que están en distintas categorías se
aplican comparando sus respectivas categorías principales.

SEMÁNTICA DE LAS RESTRICCIONES
--------------------------------
co_local_comp(ck, A, B):
  "Cuando A juega de LOCAL en su torneo ck → B no puede salir de VISITA"
  es_local_comp[ck,A,d] + es_visitante[B,d] <= 1
  es_local[B,d] + es_visitante_comp[ck,A,d] <= 1  (bidireccional)

cross_bilateral_comp(ck_A, A, ck_B, B):
  "A y B siempre tienen condiciones OPUESTAS en sus respectivos torneos principales"
  es_local_comp[ck_A,A,d] + es_local_comp[ck_B,B,d] <= 1
  es_visitante_comp[ck_A,A,d] + es_visitante_comp[ck_B,B,d] <= 1

cross_to_global_comp(ck_A, A, B):
  "A local en ck_A → B (que solo tiene una competencia) no puede ser local"
  es_local_comp[ck_A,A,d] + es_local[B,d] <= 1
  es_visitante_comp[ck_A,A,d] + es_visitante[B,d] <= 1
"""

import json
import os
import sys
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
    print(f"❌ No se encontró '{EQUIPOS_JSON}'.")
    sys.exit(1)

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

def rondas(n):
    return (n - 1) * 2 if n % 2 == 0 else n * 2

COMPETITIONS = {}
for ck, cats, div in COMP_DEFS:
    parts = sorted({
        e["nombre"] for e in equipos_data
        if any(tiene_cat(e, c) for c in cats)
        and (div is None or e.get("divisionMayor") == div)
    })
    if len(parts) >= 2:
        COMPETITIONS[ck] = {"entities": parts, "max_rondas": rondas(len(parts))}

NUM_FECHAS = 26

print("=== COMPETENCIAS ===")
for ck, comp in COMPETITIONS.items():
    n = len(comp["entities"])
    print(f"  {ck:12s}: {n:2d} equipos · {n-1:2d} locales/equipo · {comp['max_rondas']:2d} rondas · max_fecha={NUM_FECHAS}")

all_entities = sorted({n for comp in COMPETITIONS.values() for n in comp["entities"]})

# ══════════════════════════════════════════════════════════════════════════════
# 3. MODELO
# ══════════════════════════════════════════════════════════════════════════════
model = cp_model.CpModel()

# ── Variables de partido ──────────────────────────────────────────────────────
match = {}
for ck, comp in COMPETITIONS.items():
    for d in range(NUM_FECHAS):
        for i, j in combinations(comp["entities"], 2):
            match[d, ck, i, j] = model.NewBoolVar(f"m_{d}_{ck}_{i}__{j}")
            match[d, ck, j, i] = model.NewBoolVar(f"m_{d}_{ck}_{j}__{i}")

# ── Variables globales (OR de todas las competencias del equipo) ──────────────
es_local     = {(d, n): model.NewBoolVar(f"L_{d}_{n}") for d in range(NUM_FECHAS) for n in all_entities}
es_visitante = {(d, n): model.NewBoolVar(f"V_{d}_{n}") for d in range(NUM_FECHAS) for n in all_entities}

# ── Variables por competencia ─────────────────────────────────────────────────
es_lc = {}  # es_local_comp[d, ck, n]
es_vc = {}  # es_visitante_comp[d, ck, n]
for ck, comp in COMPETITIONS.items():
    for n in comp["entities"]:
        for d in range(NUM_FECHAS):
            es_lc[d, ck, n] = model.NewBoolVar(f"Lc_{d}_{ck}_{n}")
            es_vc[d, ck, n] = model.NewBoolVar(f"Vc_{d}_{ck}_{n}")

# ══════════════════════════════════════════════════════════════════════════════
# 4. RESTRICCIONES DE TORNEO
# ══════════════════════════════════════════════════════════════════════════════
for ck, comp in COMPETITIONS.items():
    ents = comp["entities"]

    for i, j in combinations(ents, 2):
        model.Add(sum(match[d, ck, i, j] for d in range(NUM_FECHAS)) == 1)
        model.Add(sum(match[d, ck, j, i] for d in range(NUM_FECHAS)) == 1)

    for d in range(NUM_FECHAS):
        for i in ents:
            apars = (
                [match[d, ck, i, j] for j in ents if j != i] +
                [match[d, ck, j, i] for j in ents if j != i]
            )
            model.Add(sum(apars) <= 1)

# ══════════════════════════════════════════════════════════════════════════════
# 5. CONSOLIDACIÓN DE VARIABLES
# ══════════════════════════════════════════════════════════════════════════════
for n in all_entities:
    for d in range(NUM_FECHAS):
        # Variables por competencia
        for ck, comp in COMPETITIONS.items():
            if n not in comp["entities"]:
                continue
            l_ck = [match[d, ck, n, j] for j in comp["entities"] if j != n]
            v_ck = [match[d, ck, j, n] for j in comp["entities"] if j != n]

            for v in l_ck: model.Add(es_lc[d, ck, n] >= v)
            model.Add(es_lc[d, ck, n] <= sum(l_ck))
            for v in v_ck: model.Add(es_vc[d, ck, n] >= v)
            model.Add(es_vc[d, ck, n] <= sum(v_ck))

        # Variables globales
        l_all = [match[d, ck, n, j]
                 for ck, comp in COMPETITIONS.items()
                 if n in comp["entities"]
                 for j in comp["entities"] if j != n]
        v_all = [match[d, ck, j, n]
                 for ck, comp in COMPETITIONS.items()
                 if n in comp["entities"]
                 for j in comp["entities"] if j != n]

        if l_all:
            for v in l_all: model.Add(es_local[d, n] >= v)
            model.Add(es_local[d, n] <= sum(l_all))
        else:
            model.Add(es_local[d, n] == 0)

        if v_all:
            for v in v_all: model.Add(es_visitante[d, n] >= v)
            model.Add(es_visitante[d, n] <= sum(v_all))
        else:
            model.Add(es_visitante[d, n] == 0)

        model.Add(es_local[d, n] + es_visitante[d, n] <= 1)

# ══════════════════════════════════════════════════════════════════════════════
# 6. FUNCIONES DE RESTRICCIÓN
# ══════════════════════════════════════════════════════════════════════════════

_h2h_cache = {}

def get_is_h2h(A, B, d):
    """BoolVar = 1 si A y B se enfrentan directamente en fecha d."""
    key = (min(A, B), max(A, B), d)
    if key in _h2h_cache:
        return _h2h_cache[key]
    h2h = [match[d, ck, X, Y]
           for ck, comp in COMPETITIONS.items()
           if A in comp["entities"] and B in comp["entities"]
           for X, Y in [(A, B), (B, A)]]
    if not h2h:
        _h2h_cache[key] = None
        return None
    v = model.NewBoolVar(f"h2h_{d}_{key[0][:5]}_{key[1][:5]}")
    model.Add(sum(h2h) >= 1).OnlyEnforceIf(v)
    model.Add(sum(h2h) == 0).OnlyEnforceIf(v.Not())
    _h2h_cache[key] = v
    return v

def _are_rivals(A, B):
    return any(A in comp["entities"] and B in comp["entities"]
               for comp in COMPETITIONS.values())


def co_local_comp(ck, A, B):
    """
    CO-LOCAL desde competencia ck:
    Cuando A es local en ck → B no puede ser visitante (global).
    Bidireccional: Cuando B es local (global) → A no puede ser visitante en ck.
    Con H2H bypass si A y B son rivales directos.
    """
    if A not in all_entities or B not in all_entities:
        return
    if A not in COMPETITIONS.get(ck, {}).get("entities", []):
        print(f"  ⚠ co_local_comp({ck},{A},{B}): {A} no en {ck}")
        return

    is_rival = _are_rivals(A, B)

    for d in range(NUM_FECHAS):
        lA = es_lc[d, ck, A]
        vA = es_vc[d, ck, A]
        lB = es_local[d, B]
        vB = es_visitante[d, B]

        if is_rival:
            h2h = get_is_h2h(A, B, d)
            model.Add(lA + vB <= 1).OnlyEnforceIf(h2h.Not())
            model.Add(lB + vA <= 1).OnlyEnforceIf(h2h.Not())
        else:
            model.Add(lA + vB <= 1)
            model.Add(lB + vA <= 1)


def cross_bilateral_comp(ck_A, A, ck_B, B):
    """
    CRUCE bilateral por competencia:
    A y B tienen condiciones opuestas EN SUS RESPECTIVOS TORNEOS PRINCIPALES.
    
    - A local en ck_A → B no local en ck_B
    - A visitante en ck_A → B no visitante en ck_B
    
    Semántica: "cuando el club A recibe en su torneo, el club B sale de visita en su torneo"
    No necesita H2H bypass porque en el partido directo siempre uno es local y el otro visitante.
    """
    if A not in all_entities or B not in all_entities:
        return
    ck_A_ents = COMPETITIONS.get(ck_A, {}).get("entities", [])
    ck_B_ents = COMPETITIONS.get(ck_B, {}).get("entities", [])
    if A not in ck_A_ents:
        print(f"  ⚠ cross_bilateral_comp({ck_A},{A},{ck_B},{B}): {A} no en {ck_A}")
        return
    if B not in ck_B_ents:
        print(f"  ⚠ cross_bilateral_comp({ck_A},{A},{ck_B},{B}): {B} no en {ck_B}")
        return

    for d in range(NUM_FECHAS):
        lA = es_lc[d, ck_A, A]
        vA = es_vc[d, ck_A, A]
        lB = es_lc[d, ck_B, B]
        vB = es_vc[d, ck_B, B]

        model.Add(lA + lB <= 1)
        model.Add(vA + vB <= 1)


def cross_to_global_comp(ck_A, A, B):
    """
    CRUCE donde A tiene torneo específico y B solo tiene una competencia.
    A local en ck_A → B no local (global).
    A visitante en ck_A → B no visitante (global).
    """
    if A not in all_entities or B not in all_entities:
        return
    if A not in COMPETITIONS.get(ck_A, {}).get("entities", []):
        print(f"  ⚠ cross_to_global_comp({ck_A},{A},{B}): {A} no en {ck_A}")
        return

    for d in range(NUM_FECHAS):
        lA = es_lc[d, ck_A, A]
        vA = es_vc[d, ck_A, A]
        lB = es_local[d, B]
        vB = es_visitante[d, B]

        model.Add(lA + lB <= 1)
        model.Add(vA + vB <= 1)


# ══════════════════════════════════════════════════════════════════════════════
# 7. REGLAS POR CLUB
# ══════════════════════════════════════════════════════════════════════════════

print("\nAplicando restricciones cruzadas...")

# ── Independiente (azul, A) - PRIMERA_A ──────────────────────────────────────
# Femenino cruzado (regla general). Ind solo tiene FEMENINO como satélite.
cross_to_global_comp("PRIMERA_A", "Independiente", "Independiente Femenino")

# ── Independiente Rojo - INF_B ────────────────────────────────────────────────
# Cruce con Independiente azul (comparten estadio, INF_B vs PRIMERA_A)
cross_bilateral_comp("INF_B", "Independiente (rojo)", "PRIMERA_A", "Independiente")
# Rojo CRUZA con Femenino (cuando Rojo local -> Femenino visitante)
cross_bilateral_comp("INF_B", "Independiente (rojo)", "FEMENINO", "Independiente Femenino")

# ── BOTAFOGO - PRIMERA_B ─────────────────────────────────────────────────────
co_local_comp("PRIMERA_B", "BOTAFOGO F.C.", "BOTAFOGO F.C. Inferiores")

# ── Ferrocarril Sud - PRIMERA_A ───────────────────────────────────────────────
# Femenino cruzado (regla general)
cross_to_global_comp("PRIMERA_A", "Ferrocarril Sud", "Ferrocarril Sud Femenino")

# ── Ferro Azul - INF_B ────────────────────────────────────────────────────────
# Cruce con Ferrocarril Sud (comparten estadio)
cross_bilateral_comp("INF_B", "Ferro Azul", "PRIMERA_A", "Ferrocarril Sud")
# Ferro Azul CRUZA con Femenino (cuando Azul local -> Femenino visitante)
cross_bilateral_comp("INF_B", "Ferro Azul", "FEMENINO", "Ferrocarril Sud Femenino")

# ── Defensores de Ayacucho - PRIMERA_A ───────────────────────────────────────
co_local_comp("PRIMERA_A", "DEFENSORES DE AYACUCHO", "DEFENSORES DE AYACUCHO Inferiores")

# ── Velense - PRIMERA_A ───────────────────────────────────────────────────────
co_local_comp("PRIMERA_A", "Velense", "Velense Inferiores")

# ── Argentino - PRIMERA_B ─────────────────────────────────────────────────────
co_local_comp("PRIMERA_B", "Argentino", "Argentino Inferiores")

# ── San José - PRIMERA_B ──────────────────────────────────────────────────────
co_local_comp("PRIMERA_B", "San José", "San José Inferiores")
# Cruce con Excursionistas (ambos en PRIMERA_B)
cross_bilateral_comp("PRIMERA_B", "San José", "PRIMERA_B", "Excursionistas")
# Cruce con Excursionistas Femenino
cross_to_global_comp("PRIMERA_B", "San José", "Excursionistas Femenino")

# ── Excursionistas - PRIMERA_B + INF_B ───────────────────────────────────────
# Co-local desde PRIMERA_B con femenino
cross_to_global_comp("PRIMERA_B", "Excursionistas", "Excursionistas Femenino")
# cross con San José ya aplicado

# ── Alumni - PRIMERA_B ────────────────────────────────────────────────────────
co_local_comp("PRIMERA_B", "Alumni", "Alumni Inferiores")
# Cruce con Juarense (PRIMERA_A vs PRIMERA_B)
cross_bilateral_comp("PRIMERA_B", "Alumni", "PRIMERA_A", "Juarense")

# ── Deportivo Tandil - PRIMERA_A ─────────────────────────────────────────────
co_local_comp("PRIMERA_A", "Deportivo Tandil", "Deportivo Tandil Inferiores")
# Cruce con Juventud Unida Fem (Blanco) - solo FEMENINO
cross_to_global_comp("PRIMERA_A", "Deportivo Tandil", "Juventud Unida Fem (Blanco)")
# Cruce con Defensores del Cerro (PRIMERA_B)
cross_bilateral_comp("PRIMERA_A", "Deportivo Tandil", "PRIMERA_B", "Defensores del Cerro")

# ── Defensores del Cerro - PRIMERA_B ─────────────────────────────────────────
co_local_comp("PRIMERA_B", "Defensores del Cerro", "Defensores del Cerro Inferiores")
# Co-local con Juventud Unida Fem (Blanco)
co_local_comp("PRIMERA_B", "Defensores del Cerro", "Juventud Unida Fem (Blanco)")
# cross con Deportivo Tandil ya aplicado

# ── Loma Negra - PRIMERA_B ────────────────────────────────────────────────────
# EXCEPCIÓN: femenino co-local (no cruce)
co_local_comp("PRIMERA_B", "Loma Negra", "Loma Negra Inferiores")
co_local_comp("PRIMERA_B", "Loma Negra", "Loma Negra Femenino")

# ── Juarense - PRIMERA_A + INF_A ─────────────────────────────────────────────
# Femenino cruzado
cross_to_global_comp("PRIMERA_A", "Juarense", "Juarense Femenino")
# cross con Alumni ya aplicado

# ── UNICEN - PRIMERA_A + INF_A ───────────────────────────────────────────────
# Cruce con Grupo Universitario (PRIMERA_B)
cross_bilateral_comp("PRIMERA_A", "UNICEN", "PRIMERA_B", "Grupo Universitario")

# ── Atlético Ayacucho - PRIMERA_A ────────────────────────────────────────────
co_local_comp("PRIMERA_A", "ATLETICO AYACUCHO", "ATLETICO AYACUCHO Inferiores")
# Femenino cruzado
cross_to_global_comp("PRIMERA_A", "ATLETICO AYACUCHO", "ATLETICO AYACUCHO Femenino")

# ── Sarmiento Ayacucho - PRIMERA_A ───────────────────────────────────────────
co_local_comp("PRIMERA_A", "SARMIENTO (AYACUCHO)", "SARMIENTO (AYACUCHO) Inferiores")
# Cruce con Ateneo Estrada (PRIMERA_B)
cross_bilateral_comp("PRIMERA_A", "SARMIENTO (AYACUCHO)", "PRIMERA_B", "ATENEO ESTRADA")

# ── Ateneo Estrada - PRIMERA_B ────────────────────────────────────────────────
co_local_comp("PRIMERA_B", "ATENEO ESTRADA", "ATENEO ESTRADA Inferiores")
# cross con Sarmiento ya aplicado

# ── Deportivo Rauch - PRIMERA_B ───────────────────────────────────────────────
co_local_comp("PRIMERA_B", "DEPORTIVO RAUCH", "DEPORTIVO RAUCH Inferiores")

# ── Santamarina - PRIMERA_A + INF_A ──────────────────────────────────────────
# Femenino cruzado
cross_to_global_comp("PRIMERA_A", "Santamarina", "Santamarina Femenino")
# Cruce con Oficina (PRIMERA_B)
cross_bilateral_comp("PRIMERA_A", "Santamarina", "PRIMERA_B", "Oficina")

# ── Gimnasia y Esgrima - PRIMERA_A + INF_A ───────────────────────────────────
# Femenino cruzado
cross_to_global_comp("PRIMERA_A", "Gimnasia y Esgrima", "Gimnasia y Esgrima Femenino")

# ── Oficina - PRIMERA_B + INF_B ───────────────────────────────────────────────
# Cruce con Santamarina ya aplicado.
# "Oficina local → Santamarina Femenino local" → co_local desde PRIMERA_B
co_local_comp("PRIMERA_B", "Oficina", "Santamarina Femenino")

# ── Juventud Unida - PRIMERA_A + INF_A ───────────────────────────────────────
co_local_comp("PRIMERA_A", "Juventud Unida", "Juventud Unida Infantiles")
# Cruce con Unión y Progreso (PRIMERA_B)
cross_bilateral_comp("PRIMERA_A", "Juventud Unida", "PRIMERA_B", "Unión y Progreso")
# Co-local con San José Femenino y JU Fem Negro
co_local_comp("PRIMERA_A", "Juventud Unida", "San José Femenino")
co_local_comp("PRIMERA_A", "Juventud Unida", "Juventud Unida Fem (Negro)")

# ── Unión y Progreso - PRIMERA_B + INF_B ─────────────────────────────────────
# Cruce con JU ya aplicado.
# Cruce con San José Femenino y JU Fem Negro
cross_to_global_comp("PRIMERA_B", "Unión y Progreso", "San José Femenino")
cross_to_global_comp("PRIMERA_B", "Unión y Progreso", "Juventud Unida Fem (Negro)")

# ── San Lorenzo Rauch - PRIMERA_B ────────────────────────────────────────────
co_local_comp("PRIMERA_B", "SAN LORENZO (RAUCH)", "SAN LORENZO (RAUCH) Inferiores")
co_local_comp("PRIMERA_B", "SAN LORENZO (RAUCH)", "SAN LORENZO (RAUCH) Femenino")  # sub16 solo, no hay conflicto de cancha

# ══════════════════════════════════════════════════════════════════════════════
# 8. SEGURIDAD POLICIAL: AYACUCHO ≤ 2 LOCALES SIMULTÁNEOS
# ══════════════════════════════════════════════════════════════════════════════
ayacucho = [n for n in [
    "DEFENSORES DE AYACUCHO",
    "ATLETICO AYACUCHO",
    "SARMIENTO (AYACUCHO)",
    "ATENEO ESTRADA",
] if n in all_entities]

for d in range(NUM_FECHAS):
    model.Add(sum(es_local[d, n] for n in ayacucho) <= 2)

# ══════════════════════════════════════════════════════════════════════════════
# 9. RACHAS: MÁXIMO 3 CONSECUTIVOS + MINIMIZACIÓN SOFT
# ══════════════════════════════════════════════════════════════════════════════
# Se aplica uniformemente a TODOS los equipos (igualitario).
# Máximo absoluto: 3 seguidos (duro).
# Objetivo: minimizar ventanas de exactamente 3 (soft).
penalties = []

for n in all_entities:
    for d in range(NUM_FECHAS - 3):
        model.Add(sum(es_local[d+k, n]     for k in range(4)) <= 3)
        model.Add(sum(es_visitante[d+k, n] for k in range(4)) <= 3)

    for d in range(NUM_FECHAS - 2):
        pl = model.NewBoolVar(f"pl_{n}_{d}")
        s3l = sum(es_local[d+k, n] for k in range(3))
        model.Add(s3l == 3).OnlyEnforceIf(pl)
        model.Add(s3l <= 2).OnlyEnforceIf(pl.Not())
        penalties.append(pl)

        pv = model.NewBoolVar(f"pv_{n}_{d}")
        s3v = sum(es_visitante[d+k, n] for k in range(3))
        model.Add(s3v == 3).OnlyEnforceIf(pv)
        model.Add(s3v <= 2).OnlyEnforceIf(pv.Not())
        penalties.append(pv)

model.Minimize(sum(penalties))

# ══════════════════════════════════════════════════════════════════════════════
# 10. RESOLUCIÓN
# ══════════════════════════════════════════════════════════════════════════════
print(f"\n🔄 Resolviendo modelo CP-SAT...")
print(f"   Equipos: {len(all_entities)} · Fechas: {NUM_FECHAS}")
print(f"   Variables de partido: {len(match)}")

solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 300.0
solver.parameters.num_search_workers  = 8
solver.parameters.log_search_progress = True   # Progreso visible en consola

status = solver.Solve(model)

STATUS_TXT = {
    cp_model.OPTIMAL:    "✅ ÓPTIMO",
    cp_model.FEASIBLE:   "⚡ FACTIBLE (tiempo agotado antes del óptimo)",
    cp_model.INFEASIBLE: "❌ INFACTIBLE",
    cp_model.UNKNOWN:    "❓ DESCONOCIDO (tiempo agotado sin solución)",
}
print(f"\nEstado: {STATUS_TXT.get(status, str(status))}")

if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
    fixture = []
    for ck, comp in COMPETITIONS.items():
        for d in range(NUM_FECHAS):
            for i in comp["entities"]:
                for j in comp["entities"]:
                    if i != j and (d, ck, i, j) in match:
                        if solver.Value(match[d, ck, i, j]) == 1:
                            fixture.append({
                                "competencia": ck,
                                "fecha":       d + 1,
                                "local":       i,
                                "visitante":   j,
                                "estadio":     estadio_de.get(i, "A confirmar"),
                            })

    fixture.sort(key=lambda x: (x["competencia"], x["fecha"], x["local"]))

    out = os.path.join(SCRIPT_DIR, "fixture_output.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(fixture, fh, indent=4, ensure_ascii=False)

    print(f"✅ {len(fixture)} partidos exportados → {out}")
    print(f"   Penalización total (rachas de 3): {int(solver.ObjectiveValue())}")

    from collections import Counter
    cnt = Counter(p["competencia"] for p in fixture)
    print("\n=== RESUMEN POR COMPETENCIA ===")
    for ck in sorted(cnt):
        n   = len(COMPETITIONS[ck]["entities"])
        exp = n * (n - 1)
        ok  = "✓" if cnt[ck] == exp else "⚠"
        print(f"  {ok} {ck:12s}: {cnt[ck]:4d} partidos (esperados {exp:4d})")

    # Mini-verificación de restricciones
    print("\n=== VERIFICACIÓN DE RESTRICCIONES (muestra) ===")
    samples = [
        ("co_local", "PRIMERA_B", "Loma Negra", "Loma Negra Femenino"),
        ("co_local", "PRIMERA_A", "Juventud Unida", "San José Femenino"),
        ("co_local", "PRIMERA_A", "Deportivo Tandil", "Deportivo Tandil Inferiores"),
    ]
    violations = 0
    for rtype, ck, A, B in samples:
        if A not in all_entities or B not in all_entities: continue
        if A not in COMPETITIONS.get(ck, {}).get("entities", []): continue
        for d in range(NUM_FECHAS):
            lA = solver.Value(es_lc[d, ck, A])
            vB = solver.Value(es_visitante[d, B])
            vA = solver.Value(es_vc[d, ck, A])
            lB = solver.Value(es_local[d, B])
            if lA + vB > 1 or vA + lB > 1:
                violations += 1
                print(f"  ⚠ F{d+1}: {A}(L={lA},V={vA}) | {B}(L={lB},V={vB})")
    if violations == 0:
        print("  ✅ Sin violaciones en la muestra verificada.")

else:
    print("\n❌ No se encontró solución.")
    print("DIAGNÓSTICO:")
    print("  Cambiar log_search_progress=True ya está activado para ver el solver.")
    print("  Si el solver dice INFEASIBLE desde el principio, hay un conflicto lógico.")
    print("  Intentar comentar el bloque 9 (rachas) para aislar el problema.")
    print("  Intentar aumentar max_time_in_seconds a 600 si el estado es UNKNOWN.")
