
for d in range(num_fechas):

    # ==========================================
    # 1. BLOQUE INDEPENDIENTE Y FERRO
    # ==========================================
    # Acompañan
    model.Add(es_local[d, "Independiente (rojo)"] == es_local[d, "Independiente Femenino"])
    model.Add(es_local[d, "Ferro Azul"] == es_local[d, "Ferrocarril Sud Femenino"])
    
    # Cruzan
    model.Add(es_local[d, "Independiente"] != es_local[d, "Independiente Femenino"])
    model.Add(es_local[d, "Independiente"] != es_local[d, "Independiente (rojo)"])
    model.Add(es_local[d, "Ferrocarril Sud"] != es_local[d, "Ferrocarril Sud Femenino"])
    model.Add(es_local[d, "Ferrocarril Sud"] != es_local[d, "Ferro Azul"])

    # ==========================================
    # 2. BLOQUE ALUMNI / DEFENSORES / DEP. TANDIL / JUARENSE
    # ==========================================
    # Acompañan
    model.Add(es_local[d, "Alumni"] == es_local[d, "Alumni/Defensores del Cerro Inferiores"])
    model.Add(es_local[d, "Alumni"] == es_local[d, "Defensores del Cerro"])
    model.Add(es_local[d, "Defensores del Cerro"] == es_local[d, "Juventud Unida Fem (Blanco)"])
    model.Add(es_local[d, "Deportivo Tandil"] == es_local[d, "Deportivo Tandil Inferiores"])

    # Cruzan
    model.Add(es_local[d, "Alumni"] != es_local[d, "Juarense"])
    model.Add(es_local[d, "Defensores del Cerro"] != es_local[d, "Juarense"])
    model.Add(es_local[d, "Defensores del Cerro"] != es_local[d, "Deportivo Tandil"])
    model.Add(es_local[d, "Deportivo Tandil"] != es_local[d, "Juventud Unida Fem (Blanco)"])
    model.Add(es_local[d, "Juarense"] != es_local[d, "Juarense Femenino"])

    # ==========================================
    # 3. BLOQUE SAN JOSÉ / EXCURSIONISTAS
    # ==========================================
    # Acompañan
    model.Add(es_local[d, "San José"] == es_local[d, "San José Inferiores"])
    model.Add(es_local[d, "Excursionistas"] == es_local[d, "Excursionistas Femenino"])

    # Cruzan
    model.Add(es_local[d, "San José"] != es_local[d, "Excursionistas"])

    # ==========================================
    # 4. BLOQUE JUVENTUD UNIDA / UNIÓN Y PROGRESO
    # ==========================================
    # Acompañan
    model.Add(es_local[d, "Juventud Unida"] == es_local[d, "Juventud Unida Infantiles"])
    model.Add(es_local[d, "Juventud Unida"] == es_local[d, "San José Femenino"])
    model.Add(es_local[d, "Juventud Unida"] == es_local[d, "Juventud Unida Fem (Negro)"])

    # Cruzan
    model.Add(es_local[d, "Juventud Unida"] != es_local[d, "Unión y Progreso"])

    # ==========================================
    # 5. BLOQUE SANTAMARINA / OFICINA
    # ==========================================
    # Acompañan
    model.Add(es_local[d, "Oficina"] == es_local[d, "Santamarina Femenino"])

    # Cruzan
    model.Add(es_local[d, "Santamarina"] != es_local[d, "Oficina"])
    model.Add(es_local[d, "Santamarina"] != es_local[d, "Santamarina Femenino"])

    # ==========================================
    # 6. BLOQUE UNICEN / GRUPO UNIV. Y GIMNASIA
    # ==========================================
    # Cruzan Clásicos Directos
    model.Add(es_local[d, "UNICEN"] != es_local[d, "Grupo Universitario"])
    model.Add(es_local[d, "Gimnasia y Esgrima"] != es_local[d, "Gimnasia y Esgrima Femenino"])

    # ==========================================
    # 7. BLOQUE AYACUCHO Y RAUCH (Masc e Inf compartidos)
    # ==========================================
    # Acompañan
    model.Add(es_local[d, "ATLETICO AYACUCHO"] == es_local[d, "ATLETICO AYACUCHO Inferiores"])
    model.Add(es_local[d, "SARMIENTO (AYACUCHO)"] == es_local[d, "SARMIENTO (AYACUCHO) Inferiores"])
    model.Add(es_local[d, "DEFENSORES DE AYACUCHO"] == es_local[d, "DEFENSORES DE AYACUCHO Inferiores"])
    
    # ¡Atención regla 7 y 21 unificadas!
    model.Add(es_local[d, "DEPORTIVO RAUCH"] == es_local[d, "ATENEO ESTRADA/Deportivo Rauch Inferiores"])
    
    # Cruzan
    model.Add(es_local[d, "ATLETICO AYACUCHO"] != es_local[d, "ATLETICO AYACUCHO Femenino"])
    model.Add(es_local[d, "SARMIENTO (AYACUCHO)"] != es_local[d, "ATENEO ESTRADA"])

    # Restricción Policial Ayacucho (Máximo 2 locales)
    model.Add(
        es_local[d, "DEFENSORES DE AYACUCHO"] + 
        es_local[d, "ATLETICO AYACUCHO"] + 
        es_local[d, "SARMIENTO (AYACUCHO)"] + 
        es_local[d, "ATENEO ESTRADA"] <= 2
    )

    # ==========================================
    # 8. EQUIPOS LINEALES DESDOBLADOS EN EL JSON
    # ==========================================
    # Acompañan (Deben replicar la localía de su Primera en todas las filiales que el JSON separó)
    model.Add(es_local[d, "Loma Negra"] == es_local[d, "Loma Negra Inferiores"])
    model.Add(es_local[d, "Loma Negra"] == es_local[d, "Loma Negra Femenino"])
    
    model.Add(es_local[d, "SAN LORENZO (RAUCH)"] == es_local[d, "SAN LORENZO (RAUCH) Inferiores"])
    model.Add(es_local[d, "SAN LORENZO (RAUCH)"] == es_local[d, "SAN LORENZO (RAUCH) Femenino"])
    
    model.Add(es_local[d, "Argentino"] == es_local[d, "Argentino Inferiores"])
    model.Add(es_local[d, "Velense"] == es_local[d, "Velense Inferiores"])
    model.Add(es_local[d, "BOTAFOGO F.C."] == es_local[d, "BOTAFOGO F.C. Inferiores"])