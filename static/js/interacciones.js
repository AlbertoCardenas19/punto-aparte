/* Menús fuera del contenedor desplazable, sin alterar acciones ni permisos. */
const menus = new Map();
document.addEventListener('show.bs.dropdown', event => {
    const toggle = event.target;
    const menu = toggle.parentElement.querySelector('.dropdown-menu');
    if (!menu || !toggle.closest('.table-responsive')) return;
    const marker = document.createComment('menu');
    menu.before(marker);
    menus.set(toggle, {menu, marker});
    document.body.append(menu);
});
document.addEventListener('hidden.bs.dropdown', event => {
    const entry = menus.get(event.target);
    if (entry) { entry.marker.replaceWith(entry.menu); menus.delete(event.target); }
});

for (const form of document.querySelectorAll('[data-busqueda-viva]')) {
    const input = form.querySelector('[name="q"]');
    const status = document.createElement('p');
    status.className = 'small text-secondary mt-2';
    status.setAttribute('role', 'status');
    form.append(status);
    let timer, controller, version = 0;
    input.addEventListener('input', () => {
        clearTimeout(timer);
        controller?.abort();
        const current = ++version;
        timer = setTimeout(async () => {
            controller = new AbortController();
            const url = new URL(form.action || location.href);
            url.search = new URLSearchParams(new FormData(form)).toString();
            const results = document.querySelector('[data-resultados-busqueda]');
            results.setAttribute('aria-busy', 'true');
            status.textContent = 'Buscando…';
            try {
                const response = await fetch(url, {signal: controller.signal});
                if (!response.ok) throw new Error('HTTP');
                const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
                const next = doc.querySelector('[data-resultados-busqueda]');
                if (!next) throw new Error('Resultados no disponibles');
                if (current !== version) return;
                for (const [toggle, entry] of menus) {
                    bootstrap.Dropdown.getInstance(toggle)?.hide();
                    entry.menu.remove(); menus.delete(toggle);
                }
                results.replaceWith(next);
                history.replaceState(null, '', url);
                status.textContent = 'Resultados actualizados.';
            } catch (error) {
                if (current === version && error.name !== 'AbortError') status.textContent = 'No se pudo actualizar. Usa Buscar para intentarlo de nuevo.';
            } finally {
                if (current === version) document.querySelector('[data-resultados-busqueda]').removeAttribute('aria-busy');
            }
        }, 300);
    });
}
const copy = document.querySelector('[data-copiar-password]');
copy?.addEventListener('click', async () => {
    const input = document.querySelector('#password-temporal');
    const status = document.querySelector('[data-estado-copia]');
    try { await navigator.clipboard.writeText(input.value); status.textContent = 'Contraseña copiada.'; }
    catch { input.select(); status.textContent = 'Seleccionada. Copia con Ctrl+C o con la opción Copiar del dispositivo.'; }
});

// Evita recuperar la contraseña temporal desde el historial de navegación.
window.addEventListener('pagehide', () => {
    const temporal = document.querySelector('#password-temporal');
    if (temporal) { temporal.value = ''; temporal.defaultValue = ''; }
});
