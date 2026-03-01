/* ====================================================
   MultiMachine Controller — app.js
   ==================================================== */

let _pcs = [];

// ---- Data loading ----

async function loadPCs() {
  try {
    const res = await fetch('/api/status');
    _pcs = await res.json();
    renderPCs(_pcs);
    updateStats(_pcs);
  } catch (err) {
    showToast('Error al cargar equipos: ' + err.message, 'error');
  }
}

function updateStats(pcs) {
  const online = pcs.filter(p => p.connected).length;
  document.getElementById('stat-total').textContent = pcs.length;
  document.getElementById('stat-online').textContent = online;
  document.getElementById('stat-offline').textContent = pcs.length - online;
  const now = new Date();
  document.getElementById('stat-time').textContent =
    now.toLocaleTimeString('es-ES');
}

// ---- Render PC cards ----

function renderPCs(pcs) {
  const container = document.getElementById('pc-container');
  container.innerHTML = '';

  if (pcs.length === 0) {
    container.innerHTML = `
      <div class="loading-placeholder">
        <i data-lucide="server-off" class="loading-icon"></i>
        <p>No hay equipos configurados. Agrega uno con el botón "Agregar PC".</p>
      </div>`;
    lucide.createIcons();
    return;
  }

  pcs.forEach(pc => {
    const card = document.createElement('div');
    card.className = 'glass-card pc-card card-enter';

    if (pc.connected) {
      card.innerHTML = buildOnlineCard(pc);
    } else {
      card.innerHTML = buildOfflineCard(pc);
    }

    container.appendChild(card);
  });

  lucide.createIcons();
}

function buildOnlineCard(pc) {
  return `
    <div class="pc-card-header">
      <div class="pc-card-info">
        <div class="pc-card-avatar pc-card-avatar-online">
          <i data-lucide="monitor-check"></i>
        </div>
        <div>
          <div class="pc-card-name" title="${esc(pc.name)}">${esc(pc.name)}</div>
          <div class="pc-card-ip">${esc(pc.ip)}:${pc.port}</div>
        </div>
      </div>
      <button class="btn-icon btn-icon-danger" title="Eliminar PC"
              onclick="removePC('${pc.id}','${esc(pc.name)}')">
        <i data-lucide="trash-2"></i>
        <span>Eliminar</span>
      </button>
    </div>
    <div class="status-row">
      <div class="status-dot status-dot-online"></div>
      <span class="status-text-online">Conectado</span>
      ${pc.hostname ? `<span class="status-hostname">· ${esc(pc.hostname)}</span>` : ''}
    </div>
    ${pc.os ? `<div class="status-os">${esc(pc.os)}</div>` : ''}
    <div class="cmd-grid">
      <button class="btn-icon" title="Info del sistema" onclick="sendCommand('${pc.id}',{command:'INFO'})">
        <i data-lucide="cpu"></i><span>Info</span>
      </button>
      <button class="btn-icon" title="Listar procesos" onclick="sendCommand('${pc.id}',{command:'LIST_PROCESSES'})">
        <i data-lucide="list"></i><span>Procesos</span>
      </button>
      <button class="btn-icon" title="Lanzar aplicación" onclick="openAppLauncher('${pc.id}','${esc(pc.name)}')">
        <i data-lucide="rocket"></i><span>App</span>
      </button>
      <button class="btn-icon" title="Bloquear pantalla" onclick="sendCommand('${pc.id}',{command:'LOCK_PC'})">
        <i data-lucide="lock"></i><span>Bloquear</span>
      </button>
      <button class="btn-icon btn-icon-danger" title="Apagar" onclick="openShutdownConfirm('${pc.id}','${esc(pc.name)}')">
        <i data-lucide="power"></i><span>Apagar</span>
      </button>
      <button class="btn-icon" title="Abrir URL" onclick="openURLSender('${pc.id}','${esc(pc.name)}')">
        <i data-lucide="globe"></i><span>URL</span>
      </button>
      <button class="btn-icon" title="Escribir archivo" onclick="openMessageSender('${pc.id}','${esc(pc.name)}')">
        <i data-lucide="file-text"></i><span>Archivo</span>
      </button>
      <button class="btn-icon" title="Cerrar aplicación" onclick="openCloseApp('${pc.id}','${esc(pc.name)}')">
        <i data-lucide="x-circle"></i><span>Cerrar App</span>
      </button>
      <button class="btn-icon" title="Cancelar apagado" onclick="sendCommand('${pc.id}',{command:'CANCEL_SHUTDOWN'})">
        <i data-lucide="shield-off"></i><span>Cancel. Apagado</span>
      </button>
      <button class="btn-icon" title="Ping" onclick="sendCommand('${pc.id}',{command:'PING'})">
        <i data-lucide="activity"></i><span>Ping</span>
      </button>
    </div>`;
}

function buildOfflineCard(pc) {
  return `
    <div class="pc-card-header">
      <div class="pc-card-info">
        <div class="pc-card-avatar pc-card-avatar-offline">
          <i data-lucide="monitor-x"></i>
        </div>
        <div>
          <div class="pc-card-name" title="${esc(pc.name)}">${esc(pc.name)}</div>
          <div class="pc-card-ip">${esc(pc.ip)}:${pc.port}</div>
        </div>
      </div>
      <button class="btn-icon btn-icon-danger" title="Eliminar PC"
              onclick="removePC('${pc.id}','${esc(pc.name)}')">
        <i data-lucide="trash-2"></i>
        <span>Eliminar</span>
      </button>
    </div>
    <div class="status-row">
      <div class="status-dot status-dot-offline"></div>
      <span class="status-text-offline">Desconectado</span>
    </div>
    ${pc.error ? `<div class="error-box">${esc(pc.error)}</div>` : ''}
    <button class="btn-secondary" style="width:100%;justify-content:center;"
            onclick="reconnect('${pc.id}')">
      <i data-lucide="refresh-cw"></i> Reconectar
    </button>`;
}

// ---- Commands ----

async function sendCommand(pcId, cmd, extra) {
  const command = Object.assign({}, cmd, extra);
  showToast(`Enviando ${command.command}…`, 'info');
  try {
    const res = await fetch('/api/command', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({pc_id: pcId, command})
    });
    const data = await res.json();
    const pc = _pcs.find(p => p.id === pcId);
    showResultModal(`${command.command} — ${pc ? pc.name : pcId}`, data);
    showToast(`${command.command} completado`, 'success');
  } catch (err) {
    showToast('Error: ' + err.message, 'error');
  }
}

async function sendToAll(cmd) {
  showToast(`Enviando ${cmd.command} a todos…`, 'info');
  try {
    const res = await fetch('/api/command/all', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({command: cmd})
    });
    const data = await res.json();
    showResultModal(`${cmd.command} — Todos los equipos`, data);
  } catch (err) {
    showToast('Error: ' + err.message, 'error');
  }
}

// ---- Reconnect ----

async function reconnect(pcId) {
  showToast('Reconectando…', 'info');
  try {
    await fetch('/api/reconnect', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({pc_id: pcId})
    });
    setTimeout(loadPCs, 2000);
  } catch (err) {
    showToast('Error: ' + err.message, 'error');
  }
}

async function reconnectAll() {
  showToast('Reconectando todos los equipos…', 'info');
  try {
    await fetch('/api/reconnect', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({})
    });
    setTimeout(loadPCs, 3000);
  } catch (err) {
    showToast('Error: ' + err.message, 'error');
  }
}

// ---- PC Management ----

function openAddPCModal() {
  document.getElementById('add-name').value = '';
  document.getElementById('add-ip').value = '';
  document.getElementById('add-port').value = '6666';
  document.getElementById('add-password').value = '';
  openModal('modal-add-pc');
}

async function addPC(event) {
  event.preventDefault();
  const name = document.getElementById('add-name').value.trim();
  const ip = document.getElementById('add-ip').value.trim();
  const port = parseInt(document.getElementById('add-port').value, 10);
  const password = document.getElementById('add-password').value;
  try {
    const res = await fetch('/api/pcs', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name, ip, port, password})
    });
    if (!res.ok) {
      const err = await res.json();
      showToast('Error: ' + (err.error || 'desconocido'), 'error');
      return;
    }
    closeModal('modal-add-pc');
    showToast(`PC "${name}" agregado`, 'success');
    setTimeout(loadPCs, 1500);
  } catch (err) {
    showToast('Error: ' + err.message, 'error');
  }
}

async function removePC(id, name) {
  if (!confirm(`¿Eliminar "${name}" de la lista?`)) return;
  try {
    await fetch('/api/pcs/' + id, {method: 'DELETE'});
    showToast(`"${name}" eliminado`, 'success');
    loadPCs();
  } catch (err) {
    showToast('Error: ' + err.message, 'error');
  }
}

// ---- Modal openers for custom commands ----

function openAppLauncher(id, name) {
  document.getElementById('custom-title').textContent = `Lanzar Aplicación — ${name}`;
  document.getElementById('custom-body').innerHTML = `
    <div class="form-grid">
      <div class="form-group">
        <label class="form-label">Nombre / ruta de la aplicación</label>
        <input class="input-field" id="custom-app-name" type="text" placeholder="firefox" />
      </div>
      <div class="form-actions">
        <button class="btn-secondary" onclick="closeModal('modal-custom')">Cancelar</button>
        <button class="btn-primary" onclick="execLaunchApp('${id}')">
          <i data-lucide="rocket"></i> Lanzar
        </button>
      </div>
    </div>`;
  lucide.createIcons();
  openModal('modal-custom');
}
function execLaunchApp(id) {
  const app = document.getElementById('custom-app-name').value.trim();
  if (!app) return;
  closeModal('modal-custom');
  sendCommand(id, {command: 'LAUNCH_APP', app});
}

function openCloseApp(id, name) {
  document.getElementById('custom-title').textContent = `Cerrar Aplicación — ${name}`;
  document.getElementById('custom-body').innerHTML = `
    <div class="form-grid">
      <div class="form-group">
        <label class="form-label">Nombre del proceso o PID</label>
        <input class="input-field" id="custom-close-target" type="text" placeholder="firefox o 1234" />
      </div>
      <div class="form-actions">
        <button class="btn-secondary" onclick="closeModal('modal-custom')">Cancelar</button>
        <button class="btn-danger" onclick="execCloseApp('${id}')">
          <i data-lucide="x-circle"></i> Cerrar
        </button>
      </div>
    </div>`;
  lucide.createIcons();
  openModal('modal-custom');
}
function execCloseApp(id) {
  const target = document.getElementById('custom-close-target').value.trim();
  if (!target) return;
  closeModal('modal-custom');
  sendCommand(id, {command: 'CLOSE_APP', target});
}

function openURLSender(id, name) {
  document.getElementById('custom-title').textContent = `Abrir URL — ${name}`;
  document.getElementById('custom-body').innerHTML = `
    <div class="form-grid">
      <div class="form-group">
        <label class="form-label">URL</label>
        <input class="input-field" id="custom-url" type="text" placeholder="https://ejemplo.com" />
      </div>
      <div class="form-actions">
        <button class="btn-secondary" onclick="closeModal('modal-custom')">Cancelar</button>
        <button class="btn-info" onclick="execOpenURL('${id}')">
          <i data-lucide="globe"></i> Abrir
        </button>
      </div>
    </div>`;
  lucide.createIcons();
  openModal('modal-custom');
}
function execOpenURL(id) {
  let url = document.getElementById('custom-url').value.trim();
  if (!url) return;
  if (!url.startsWith('http://') && !url.startsWith('https://')) {
    url = 'https://' + url;
  }
  // Block dangerous URI schemes after normalization
  const lower = url.toLowerCase();
  if (!lower.startsWith('http://') && !lower.startsWith('https://')) {
    showToast('Solo se permiten URLs http:// o https://', 'error');
    return;
  }
  closeModal('modal-custom');
  sendCommand(id, {command: 'OPEN_URL', url});
}

function openMessageSender(id, name) {
  document.getElementById('custom-title').textContent = `Escribir Archivo — ${name}`;
  document.getElementById('custom-body').innerHTML = `
    <div class="form-grid">
      <div class="form-group">
        <label class="form-label">Nombre / ruta del archivo</label>
        <input class="input-field" id="custom-filename" type="text" placeholder="/tmp/mensaje.txt" />
      </div>
      <div class="form-group">
        <label class="form-label">Contenido</label>
        <textarea class="input-field" id="custom-content" rows="4" placeholder="Escribe el contenido..."></textarea>
      </div>
      <div class="form-actions">
        <button class="btn-secondary" onclick="closeModal('modal-custom')">Cancelar</button>
        <button class="btn-primary" onclick="execWriteFile('${id}')">
          <i data-lucide="save"></i> Guardar
        </button>
      </div>
    </div>`;
  lucide.createIcons();
  openModal('modal-custom');
}
function execWriteFile(id) {
  const filename = document.getElementById('custom-filename').value.trim();
  const content = document.getElementById('custom-content').value;
  if (!filename) return;
  closeModal('modal-custom');
  sendCommand(id, {command: 'WRITE_FILE', filename, content});
}

function openShutdownConfirm(id, name) {
  document.getElementById('custom-title').textContent = `Apagar — ${name}`;
  document.getElementById('custom-body').innerHTML = `
    <div class="form-grid">
      <div class="warning-box">
        ⚠️ ¡Atención! Esta acción apagará el equipo remoto. Asegúrate de haber guardado todo el trabajo.
      </div>
      <div class="form-group">
        <label class="form-label">Retraso (minutos, 0 = inmediato)</label>
        <input class="input-field" id="custom-delay" type="number" value="0" min="0" />
      </div>
      <div class="form-actions">
        <button class="btn-secondary" onclick="closeModal('modal-custom')">Cancelar</button>
        <button class="btn-danger" onclick="execShutdown('${id}')">
          <i data-lucide="power"></i> Apagar
        </button>
      </div>
    </div>`;
  lucide.createIcons();
  openModal('modal-custom');
}
function execShutdown(id) {
  const delay = parseInt(document.getElementById('custom-delay').value, 10) || 0;
  closeModal('modal-custom');
  sendCommand(id, {command: 'SHUTDOWN', delay});
}

// ---- Modal helpers ----

function openModal(id) {
  document.getElementById(id).classList.add('open');
}
function closeModal(id) {
  document.getElementById(id).classList.remove('open');
}
function closeModalOutside(event, id) {
  if (event.target.id === id) closeModal(id);
}

// ---- Result modal ----

function showResultModal(title, data) {
  document.getElementById('result-title').textContent = title;

  let text;
  if (typeof data === 'object' && data !== null && !Array.isArray(data)) {
    // Check if it's a global (all-PCs) result: keys are UUIDs
    const values = Object.values(data);
    if (values.length > 0 && values[0] && typeof values[0] === 'object' && 'name' in values[0]) {
      // Per-PC results
      text = values.map(entry => {
        const ok = entry.result && !entry.result.error;
        const emoji = ok ? '✅' : '❌';
        return `${emoji} ${entry.name}\n${JSON.stringify(entry.result, null, 2)}`;
      }).join('\n\n');
    } else {
      text = JSON.stringify(data, null, 2);
    }
  } else {
    text = JSON.stringify(data, null, 2);
  }

  document.getElementById('result-body').textContent = text;
  openModal('modal-result');
}

// ---- Toast ----

function showToast(msg, type) {
  type = type || 'info';
  const icons = {success: 'check-circle', error: 'alert-circle', info: 'info'};
  const iconName = icons[type] || 'info';

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<i data-lucide="${iconName}"></i><span>${esc(msg)}</span>`;
  document.getElementById('toast-container').appendChild(toast);
  lucide.createIcons({nodes: [toast]});

  setTimeout(() => {
    toast.classList.add('toast-fade');
    setTimeout(() => toast.remove(), 350);
  }, 4000);
}

// ---- Utility ----

function esc(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ---- Event listeners ----

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    ['modal-result', 'modal-add-pc', 'modal-custom'].forEach(id => closeModal(id));
  }
});

// ---- Init ----

loadPCs();
setInterval(loadPCs, 10000);
