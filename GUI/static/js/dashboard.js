let chartSoC = null, chartPRef = null;
const HISTORICO_LIMIT = 200;

function initCharts() {
  const ctx1 = document.getElementById('chart-soc').getContext('2d');
  chartSoC = new Chart(ctx1, {
    type: 'line',
    data: { labels: [], datasets: [] },
    options: {
      responsive: true, maintainAspectRatio: false,
      animation: false,
      plugins: { legend: { labels: { color: '#8899aa' } } },
      scales: {
        x: { ticks: { color: '#8899aa' }, grid: { color: '#1c232d' } },
        y: { min: 0, max: 1, ticks: { color: '#8899aa' }, grid: { color: '#1c232d' } }
      }
    }
  });

  const ctx2 = document.getElementById('chart-pref').getContext('2d');
  chartPRef = new Chart(ctx2, {
    type: 'line',
    data: { labels: [], datasets: [] },
    options: {
      responsive: true, maintainAspectRatio: false,
      animation: false,
      plugins: { legend: { labels: { color: '#8899aa' } } },
      scales: {
        x: { ticks: { color: '#8899aa' }, grid: { color: '#1c232d' } },
        y: { ticks: { color: '#8899aa' }, grid: { color: '#1c232d' } }
      }
    }
  });
}

async function actualizar() {
  try {
    const resp = await fetch('/api/estado');
    const data = await resp.json();

    document.getElementById('badge-paso').textContent = `Paso: ${data['co-simulacion'].paso}`;
    document.getElementById('badge-estado').textContent = data['co-simulacion'].activa ? 'Activo' : 'Inactivo';
    document.getElementById('badge-estado').className = data['co-simulacion'].activa ? 'badge bg-success' : 'badge bg-secondary';
    document.getElementById('val-soc-avg').textContent = data['co-simulacion'].activa ? '--' : '--';
    document.getElementById('val-tiempo').textContent = data['co-simulacion'].tiempo.toFixed(1) + 's';
    document.getElementById('val-paso').textContent = data['co-simulacion'].paso;

    const agentes = data.agentes || {};
    const container = document.getElementById('agentes-container');
    const keys = Object.keys(agentes);
    document.getElementById('n-agentes').textContent = `${keys.length} conectados`;

    if (keys.length === 0) {
      container.innerHTML = '<div class="col-12 text-center text-gris py-3">Ningun agente conectado.</div>';
      return;
    }
    container.innerHTML = '';
    keys.forEach(id => {
      const ag = agentes[id];
      const color = ag.SoC > 0.6 ? '#22c55e' : ag.SoC > 0.3 ? '#eab308' : '#ef4444';
      container.innerHTML += `
        <div class="col-md-4 mb-2">
          <div class="card" style="background: #1c232d;">
            <div class="card-body py-2 px-3">
              <div class="d-flex justify-content-between">
                <strong>Agente ${id}</strong>
                <span class="badge badge-soc" style="background: ${color};">${(ag.SoC * 100).toFixed(1)}%</span>
              </div>
              <small class="text-gris">P_ref: ${ag.P_ref.toLocaleString()} W</small>
            </div>
          </div>
        </div>`;
    });

    if (keys.length > 0) {
      const histResp = await fetch('/api/historico?n=' + HISTORICO_LIMIT);
      const hist = await histResp.json();
      const labels = hist.map(h => h.tiempo.toFixed(1));
      const socAvgs = hist.map(h => h.SoC_avg);
      document.getElementById('val-soc-avg').textContent = socAvgs.length > 0 ? socAvgs[socAvgs.length - 1].toFixed(4) : '--';
      document.getElementById('val-demanda').textContent = hist.length > 0 ? hist[hist.length - 1].demanda.toLocaleString() + ' W' : '--';

      if (chartSoC) {
        chartSoC.data.labels = labels;
        chartSoC.data.datasets = [{
          label: 'SoC Promedio',
          data: socAvgs,
          borderColor: '#4a9eff',
          backgroundColor: 'rgba(74, 158, 255, 0.1)',
          fill: true,
          tension: 0.3,
          pointRadius: 0,
        }];
        chartSoC.update('none');
      }
    }
  } catch (e) {
    console.error('Error actualizando:', e);
  }
}

async function desplegar() {
  const N = document.getElementById('input-n').value;
  const resp = await fetch('/api/deploy', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ N: parseInt(N), modo: 'local' })
  });
  const data = await resp.json();
  document.getElementById('upload-status').innerHTML =
    `<span class="text-info">${data.mensaje}</span>`;
}

async function desplegarDocker() {
  document.getElementById('upload-status').innerHTML =
    `<span class="text-warning">Despliegue Docker iniciado (SSH a RPi)...</span>`;
}

async function limpiar() {
  document.getElementById('upload-status').innerHTML =
    `<span class="text-secondary">Simulacion detenida</span>`;
}

async function subirArchivo(event) {
  const file = event.target.files[0];
  if (!file) return;
  const tipo = document.querySelector('#perfil-tabs .nav-link.active').dataset.tipo;
  const formData = new FormData();
  formData.append('file', file);
  formData.append('tipo', tipo);

  const resp = await fetch('/api/upload', { method: 'POST', body: formData });
  const data = await resp.json();
  const status = document.getElementById('upload-status');
  if (data.ok) {
    status.innerHTML = `<span class="text-success">${data.archivo} (${data.filas} registros)</span>`;
    cargarArchivos();
  } else {
    status.innerHTML = `<span class="text-danger">${data.error}</span>`;
  }
  event.target.value = '';
}

async function cargarArchivos() {
  const resp = await fetch('/api/perfiles');
  const archivos = await resp.json();
  const container = document.getElementById('archivos-lista');
  if (archivos.length === 0) {
    container.innerHTML = '<div class="text-gris small">Ningun archivo cargado</div>';
    return;
  }
  container.innerHTML = archivos.map(a =>
    `<div class="d-flex justify-content-between small py-1 border-bottom border-secondary">
      <span>${a.nombre}</span>
      <span class="text-gris">${(a.tamano / 1024).toFixed(1)} KB</span>
    </div>`
  ).join('');
}

document.addEventListener('DOMContentLoaded', function() {
  initCharts();
  cargarArchivos();

  document.querySelectorAll('#perfil-tabs .nav-link').forEach(btn => {
    btn.addEventListener('click', function() {
      document.querySelectorAll('#perfil-tabs .nav-link').forEach(b => b.classList.remove('active'));
      this.classList.add('active');
    });
  });

  const zone = document.getElementById('upload-zone');
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.style.borderColor = '#4a9eff'; });
  zone.addEventListener('dragleave', () => { zone.style.borderColor = '#2a3340'; });
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.style.borderColor = '#2a3340';
    if (e.dataTransfer.files.length > 0) {
      document.getElementById('file-input').files = e.dataTransfer.files;
      subirArchivo({ target: { files: [e.dataTransfer.files[0]] } });
    }
  });

  setInterval(actualizar, 1000);
  actualizar();
});
