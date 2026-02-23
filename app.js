document.addEventListener('DOMContentLoaded', () => {
    const grid = document.getElementById('fixture-grid');
    const compFilter = document.getElementById('filter-competencia');
    const dateFilter = document.getElementById('filter-fecha');
    const matchCount = document.getElementById('match-count');

    let allMatches = [];
    let competitions = new Set();
    let dates = new Set();

    async function loadFixture() {
        try {
            const response = await fetch('fixture_output.csv');
            if (!response.ok) throw new Error('No se pudo cargar el archivo CSV');

            const text = await response.text();
            parseCSV(text);

            populateFilters();
            renderMatches();
        } catch (error) {
            grid.innerHTML = `<div class="loader">⚠️ Error: ${error.message}</div>`;
        }
    }

    function parseCSV(text) {
        const lines = text.trim().split('\n');
        const headers = lines[0].split(',');

        allMatches = lines.slice(1).map(line => {
            const values = line.split(',');
            const obj = {};
            headers.forEach((header, i) => {
                obj[header.trim()] = values[i].trim();
            });

            competitions.add(obj.competencia);
            dates.add(parseInt(obj.fecha));

            return obj;
        });
    }

    function populateFilters() {
        // Sort and populate competitions
        Array.from(competitions).sort().forEach(comp => {
            const opt = document.createElement('option');
            opt.value = comp;
            opt.textContent = comp;
            compFilter.appendChild(opt);
        });

        // Sort and populate dates
        Array.from(dates).sort((a, b) => a - b).forEach(date => {
            const opt = document.createElement('option');
            opt.value = date;
            opt.textContent = `Fecha ${date}`;
            dateFilter.appendChild(opt);
        });
    }

    function renderMatches() {
        const selComp = compFilter.value;
        const selDate = dateFilter.value;

        const filtered = allMatches.filter(m => {
            const matchComp = (selComp === 'ALL' || m.competencia === selComp);
            const matchDate = (selDate === 'ALL' || m.fecha === selDate);
            return matchComp && matchDate;
        });

        matchCount.textContent = filtered.length;
        grid.innerHTML = '';

        if (filtered.length === 0) {
            grid.innerHTML = '<div class="loader">No se encontraron encuentros para los filtros seleccionados.</div>';
            return;
        }

        filtered.forEach(m => {
            const card = document.createElement('div');
            card.className = 'match-card glass';

            // Generate icons based on team name hash for variety
            const hIcon = getIcon(m.local);
            const vIcon = getIcon(m.visitante);

            card.innerHTML = `
                <div class="match-header">
                    <span class="comp-tag">${m.competencia}</span>
                    <span class="date-tag">Fecha ${m.fecha}</span>
                </div>
                <div class="match-teams">
                    <div class="team-row">
                        <div class="team-icon">${hIcon}</div>
                        <span class="team-name">${m.local}</span>
                    </div>
                    <div class="vs-divider">VS</div>
                    <div class="team-row">
                        <div class="team-icon">${vIcon}</div>
                        <span class="team-name">${m.visitante}</span>
                    </div>
                </div>
            `;
            grid.appendChild(card);
        });
    }

    function getIcon(name) {
        const icons = ['⚽', '🏆', '🏘️', '⚔️', '⭐', '🔥', '🛡️', '⚡'];
        let hash = 0;
        for (let i = 0; i < name.length; i++) {
            hash = name.charCodeAt(i) + ((hash << 5) - hash);
        }
        return icons[Math.abs(hash) % icons.length];
    }

    compFilter.addEventListener('change', renderMatches);
    dateFilter.addEventListener('change', renderMatches);

    loadFixture();
});
