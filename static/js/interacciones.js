/* Menús fuera del contenedor desplazable, sin alterar acciones ni permisos. */
const menus = new Map();
document.addEventListener('show.bs.dropdown', event => {
    const toggle = event.target;
    const menu = toggle.parentElement.querySelector('.dropdown-menu');
    if (!menu || !toggle.closest('[data-tabla-listado]')) return;
    const marker = document.createComment('menu');
    menu.before(marker);
    menus.set(toggle, {menu, marker});
    document.body.append(menu);
});
document.addEventListener('hidden.bs.dropdown', event => {
    const entry = menus.get(event.target);
    if (entry) { entry.marker.replaceWith(entry.menu); menus.delete(event.target); }
});

for (const table of document.querySelectorAll('[data-tabla-listado]')) {
    const noOrdenables = [...table.querySelectorAll('thead th')]
        .map((th, index) => th.hasAttribute('data-no-orden') ? index : null)
        .filter(index => index !== null);
    const ordenColumna = Number.parseInt(table.dataset.ordenColumna || '0', 10);
    const ordenDireccion = table.dataset.ordenDireccion || 'asc';

    new DataTable(table, {
        responsive: true,
        pageLength: 10,
        lengthMenu: [10, 25, 50],
        order: [[ordenColumna, ordenDireccion]],
        columnDefs: noOrdenables.length ? [{
            targets: noOrdenables,
            orderable: false,
            searchable: false,
        }] : [],
        language: {
            emptyTable: 'No hay registros para mostrar.',
            info: 'Mostrando _START_ a _END_ de _TOTAL_ registros',
            infoEmpty: 'No hay registros para mostrar.',
            infoFiltered: '(filtrados de _MAX_ registros)',
            lengthMenu: 'Mostrar _MENU_ registros',
            loadingRecords: 'Cargando…',
            processing: 'Procesando…',
            search: 'Buscar:',
            zeroRecords: 'No se encontraron coincidencias.',
            paginate: {
                first: 'Primera',
                last: 'Última',
                next: 'Siguiente',
                previous: 'Anterior',
            },
        },
    });
}

for (const form of document.querySelectorAll('[data-busqueda-viva]')) {
    const input = form.querySelector('[name="q"]');
    const status = document.createElement('p');
    status.className = 'pa-estado-breve';
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
                status.textContent = '';
            } catch (error) {
                if (current === version && error.name !== 'AbortError') status.textContent = 'No se pudo actualizar. Usa Buscar para intentarlo de nuevo.';
            } finally {
                if (current === version) document.querySelector('[data-resultados-busqueda]').removeAttribute('aria-busy');
            }
        }, 300);
    });
}

function prepararCarrito(panel = document) {
    const form = panel.querySelector('[data-carrito-form]');
    if (!form) return;

    const status = form.querySelector('[data-carrito-estado]');
    let timer;

    const ajustarBotones = input => {
        const control = input.closest('.pa-cantidad-control');
        const cantidad = Number.parseInt(input.value || '0', 10);
        const maximo = Number.parseInt(input.max, 10);
        control.querySelector('[data-cantidad-restar]').disabled = cantidad <= 0;
        control.querySelector('[data-cantidad-sumar]').disabled = cantidad >= maximo;
    };

    const normalizar = input => {
        if (input.value === '') return null;
        const maximo = Number.parseInt(input.max, 10);
        let cantidad = Number.parseInt(input.value, 10);
        if (!Number.isFinite(cantidad)) cantidad = 0;
        cantidad = Math.max(0, Math.min(cantidad, maximo));
        input.value = cantidad;
        ajustarBotones(input);
        return cantidad;
    };

    const sincronizar = async () => {
        clearTimeout(timer);
        const datos = new FormData(form);
        const controles = [...form.querySelectorAll('button, input[type="number"]')];
        controles.forEach(control => control.disabled = true);
        form.setAttribute('aria-busy', 'true');
        status.textContent = '';

        try {
            const response = await fetch(form.action || location.href, {
                method: 'POST',
                body: datos,
                headers: {'X-Requested-With': 'XMLHttpRequest'},
            });
            if (!response.ok) throw new Error('HTTP');
            const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
            const nextPanel = doc.querySelector('[data-carrito-panel]');
            if (!nextPanel) throw new Error('Carrito no disponible');

            const currentMessages = document.querySelector('[data-mensajes]');
            const nextMessages = doc.querySelector('[data-mensajes]');
            if (currentMessages && nextMessages) currentMessages.replaceWith(nextMessages);

            form.closest('[data-carrito-panel]').replaceWith(nextPanel);
            prepararCarrito(nextPanel);
        } catch (error) {
            form.removeAttribute('aria-busy');
            controles.forEach(control => control.disabled = false);
            form.querySelectorAll('.pa-cantidad-valor').forEach(ajustarBotones);
            status.textContent = 'No se pudo actualizar la compra. Intenta nuevamente.';
        }
    };

    const programarSincronizacion = demora => {
        clearTimeout(timer);
        timer = setTimeout(sincronizar, demora);
    };

    for (const input of form.querySelectorAll('.pa-cantidad-valor')) {
        ajustarBotones(input);
        input.addEventListener('input', () => {
            if (normalizar(input) !== null) programarSincronizacion(350);
        });
        input.addEventListener('change', () => {
            if (input.value === '') input.value = '0';
            normalizar(input);
            programarSincronizacion(0);
        });

        const control = input.closest('.pa-cantidad-control');
        control.querySelector('[data-cantidad-restar]').addEventListener('click', () => {
            input.value = Math.max(0, Number.parseInt(input.value || '0', 10) - 1);
            ajustarBotones(input);
            programarSincronizacion(120);
        });
        control.querySelector('[data-cantidad-sumar]').addEventListener('click', () => {
            const maximo = Number.parseInt(input.max, 10);
            input.value = Math.min(maximo, Number.parseInt(input.value || '0', 10) + 1);
            ajustarBotones(input);
            programarSincronizacion(120);
        });
    }

    form.addEventListener('submit', event => {
        event.preventDefault();
        sincronizar();
    });
}

prepararCarrito();
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
