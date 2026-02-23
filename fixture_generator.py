import json
import os
import sys
import csv
from collections import defaultdict
from itertools import combinations
from ortools.sat.python import cp_model

# ── Configuración ───────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EQUIPOS_JSON = os.path.join(SCRIPT_DIR, "equipos.json")

with open(EQUIPOS_JSON, "r", encoding="utf-8") as f:
    data = json.load(f)
equipos = data["equipos"]

def tiene_cat(e, cat_key):
    return e.get("categorias", {}).get(cat_key, False) is True

# 1. Clasificación de Competencias por DÍA
COMP_DEFS = [
    ("primera_A", "primera", "A", "DOMINGO"),
    ("primera_B", "primera", "B", "DOMINGO"),
    ("inf_A", ["quinta", "sexta", "septima", "octava", "novena", "decima", "undecima"], "A", "MIXTO"),
    ("inf_B", ["quinta", "sexta", "septima", "octava", "novena", "decima", "undecima"], "B", "MIXTO"),
    ("inf_C", ["quinta", "sexta", "septima", "octava", "novena", "decima", "undecima"], "C", "MIXTO"),
    ("femenino", ["femenino_primera", "femenino_sub16", "femenino_sub14", "femenino_sub12"], None, "SABADO"),
]

COMPETITIONS = {}
for ck, cats, div, day in COMP_DEFS:
    if isinstance(cats, str): cats = [cats]
    participants = []
    entity_cats = defaultdict(list)
    for e in equipos:
        active_cats = [c for c in cats if tiene_cat(e, c)]
        if active_cats and (div is None or e.get("divisionMayor") == div):
            participants.append(e["nombre"])
            entity_cats[e["nombre"]] = active_cats
    if len(participants) >= 2:
        n = len(participants)
        rondas = (n - 1) * 2 if n % 2 == 0 else n * 2
        COMPETITIONS[ck] = {"entities": sorted(list(set(participants))), "rondas": rondas, "dia": day, "entity_cats": entity_cats}

NUM_FECHAS = 26 

# ── Modelo ──────────────────────────────────────────────────
model = cp_model.CpModel()
all_entities = sorted(list({e["nombre"] for e in equipos}))

match = {}
for ck, comp in COMPETITIONS.items():
    ents = comp["entities"]
    for d in range(NUM_FECHAS):
        for i in ents:
            for j in ents:
                if i != j:
                    match[d, ck, i, j] = model.NewBoolVar(f"m_{d}_{ck}_{i}_{j}")

es_local_sab = {(d, n): model.NewBoolVar(f"ls_{d}_{n}") for d in range(NUM_FECHAS) for n in all_entities}
es_local_dom = {(d, n): model.NewBoolVar(f"ld_{d}_{n}") for d in range(NUM_FECHAS) for n in all_entities}
juega_condicion = {(d, n): model.NewBoolVar(f"j_{d}_{n}") for d in range(NUM_FECHAS) for n in all_entities}

# 2. Restricciones de Torneo (Round Robin)
for ck, comp in COMPETITIONS.items():
    ents = comp["entities"]
    r = comp["rondas"]
    for i in ents:
        for j in ents:
            if i == j: continue
            model.Add(sum(match[d, ck, i, j] for d in range(r)) == 1)
        for d in range(NUM_FECHAS):
            partidos = [match[d, ck, i, j] for j in ents if i != j] + [match[d, ck, j, i] for j in ents if i != j]
            model.Add(sum(partidos) <= 1)
    for d in range(r, NUM_FECHAS):
        for i in ents:
            for j in ents:
                if i != j: model.Add(match[d, ck, i, j] == 0)

# 3. Enlace con bloques de días (CORREGIDO)
for n in all_entities:
    for d in range(NUM_FECHAS):
        sab_matches = []
        dom_matches = []
        for ck, comp in COMPETITIONS.items():
            if n not in comp["entities"]: continue
            if (d, ck, n, any) in match: # Dummy check
                l_vars = [match[d, ck, n, j] for j in comp["entities"] if n != j]
                if comp["dia"] == "SABADO": sab_matches.extend(l_vars)
                elif comp["dia"] == "DOMINGO": dom_matches.extend(l_vars)
                else: # MIXTO
                    sab_matches.extend(l_vars); dom_matches.extend(l_vars)
        
        # Sintaxis correcta para "Si algun partido es local, la localia del bloque es 1"
        if sab_matches: model.AddMaxEquality(es_local_sab[d, n], sab_matches)
        else: model.Add(es_local_sab[d, n] == 0)
        
        if dom_matches: model.AddMaxEquality(es_local_dom[d, n], dom_matches)
        else: model.Add(es_local_dom[d, n] == 0)

# 4. Estadios (Capacidad: 1 club por bloque de día)
estadio_map = defaultdict(list)
for e in equipos:
    if e.get("estadioLocal"): estadio_map[e["estadioLocal"]].append(e["nombre"])

for est, mbs in estadio_map.items():
    for d in range(NUM_FECHAS):
        model.Add(sum(es_local_sab[d, n] for n in mbs) <= 1)
        model.Add(sum(es_local_dom[d, n] for n in mbs) <= 1)


acompana_groups = [
    ["Independiente", "Independiente (rojo)", "Independiente Femenino"],
    ["Ferrocarril Sud", "Ferro Azul", "Ferrocarril Sud Femenino"],
    ["Santamarina", "Oficina", "Santamarina Femenino"],
    ["Juventud Unida", "Juventud Unida Infantiles", "San José Femenino", "Juventud Unida Fem (Negro)"],
    ["Alumni", "Alumni/Defensores del Cerro Inferiores", "Defensores del Cerro", "Juventud Unida Fem (Blanco)"],
    ["Deportivo Tandil", "Deportivo Tandil Inferiores"],
    ["San José", "San José Inferiores"],
    ["Excursionistas", "Excursionistas Femenino"],
    ["ATLETICO AYACUCHO", "ATLETICO AYACUCHO Inferiores", "ATLETICO AYACUCHO Femenino"],
    ["SARMIENTO (AYACUCHO)", "SARMIENTO (AYACUCHO) Inferiores"],
    ["DEFENSORES DE AYACUCHO", "DEFENSORES DE AYACUCHO Inferiores"],
    ["DEPORTIVO RAUCH", "ATENEO ESTRADA/Deportivo Rauch Inferiores"],
    ["Loma Negra", "Loma Negra Inferiores", "Loma Negra Femenino"],
    ["SAN LORENZO (RAUCH)", "SAN LORENZO (RAUCH) Inferiores", "SAN LORENZO (RAUCH) Femenino"],
    ["Argentino", "Argentino Inferiores"],
    ["Velense", "Velense Inferiores"],
    ["BOTAFOGO F.C.", "BOTAFOGO F.C. Inferiores"],
    ["UNICEN", "Grupo Universitario"] # Para que UNICEN sea local cuando Grupo es visitante
]

mirror_scores = []
for g in acompana_groups:
    ga = [n for n in g if n in all_entities]
    for A, B in combinations(ga, 2):
        for d in range(NUM_FECHAS):
            score = model.NewBoolVar(f"sc_{A}_{B}_{d}")
            # Si ambos son locales en sus respectivos días (o ambos visitantes), punto extra
            model.Add(es_local_sab[d, A] == es_local_sab[d, B]).OnlyEnforceIf(score)
            model.Add(es_local_dom[d, A] == es_local_dom[d, B]).OnlyEnforceIf(score)
            mirror_scores.append(score)

# 6. Policías y Cruces
ayacucho = ["DEFENSORES DE AYACUCHO", "ATLETICO AYACUCHO", "SARMIENTO (AYACUCHO)", "ATENEO ESTRADA"]
for d in range(NUM_FECHAS):
    model.Add(sum(es_local_dom[d, n] for n in ayacucho if n in all_entities) <= 2)

def cruzar(A, B):
    if A in all_entities and B in all_entities:
        for d in range(NUM_FECHAS):
            model.Add(es_local_dom[d, A] + es_local_dom[d, B] <= 1)
            model.Add(es_local_sab[d, A] + es_local_sab[d, B] <= 1)

for pair in [("Alumni", "Juarense"), ("San José", "Excursionistas"), ("Santamarina", "Oficina")]:
    cruzar(*pair)

model.Maximize(sum(mirror_scores))

# ── Solve ───────────────────────────────────────────────────
print("Iniciando solver...")
solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 120.0
status = solver.Solve(model)

if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
    print("❌ No se encontró solución. Relajando restricciones...")
    sys.exit(1)

# ── Export ──────────────────────────────────────────────────
COMP_LABELS = {"quinta": "5ª", "sexta": "6ª", "septima": "7ª", "octava": "8ª", "novena": "9ª", "decima": "10ª", "undecima": "11ª",
               "femenino_primera": "FEM PRIMERA", "femenino_sub16": "FEM SUB-16", "femenino_sub14": "FEM SUB-14", "femenino_sub12": "FEM SUB-12"}

rows = []
for ck, comp in COMPETITIONS.items():
    for d in range(NUM_FECHAS):
        for i in comp["entities"]:
            for j in comp["entities"]:
                if i != j and solver.Value(match[d, ck, i, j]):
                    common_cats = set(comp["entity_cats"][i]) & set(comp["entity_cats"][j])
                    if ck.startswith("primera"):
                        rows.append({"competencia": ck.upper(), "fecha": d+1, "local": i, "visitante": j})
                    else:
                        for c in sorted(list(common_cats)):
                            rows.append({"competencia": f"{ck.upper()} {COMP_LABELS.get(c, c)}", "fecha": d+1, "local": i, "visitante": j})

with open(os.path.join(SCRIPT_DIR, "fixture_output.json"), "w", encoding="utf-8") as f:
    json.dump(rows, f, indent=4, ensure_ascii=False)
print(f"✅ Fixture generado: {len(rows)} partidos.")