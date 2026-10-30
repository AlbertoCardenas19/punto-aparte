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
    const noBuscables = [...table.querySelectorAll('thead th')]
        .map((th, index) => th.hasAttribute('data-no-buscar') ? index : null)
        .filter(index => index !== null);
    const ordenColumna = Number.parseInt(table.dataset.ordenColumna || '0', 10);
    const ordenDireccion = table.dataset.ordenDireccion || 'asc';

    new DataTable(table, {
        responsive: true,
        pageLength: 10,
        lengthMenu: [10, 25, 50],
        order: [[ordenColumna, ordenDireccion]],
        columnDefs: [
            ...(noOrdenables.length ? [{
                targets: noOrdenables,
                orderable: false,
            }] : []),
            ...(noBuscables.length ? [{
                targets: noBuscables,
                searchable: false,
            }] : []),
        ],
        language: {
            emptyTable: 'No hay registros para mostrar.',
            info: 'Mostrando _START_ a _END_ de _TOTAL_ registros',
            infoEmpty: 'No hay registros para mostrar.',
            infoFiltered: '(filtrados de _MAX_ registros)',
            lengthMenu: 'Mostrar _MENU_ registros',
            loadingRecords: 'Cargando…',
            processing: 'Procesando…',
            search: 'Buscar:',
            searchPlaceholder: table.dataset.busquedaAyuda || '',
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
                prepararControlesProductos(next);
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

function ajustarBotonesCantidad(input) {
    const control = input.closest('.pa-cantidad-control');
    const cantidad = Number.parseInt(input.value || '0', 10);
    const maximo = Number.parseInt(input.max, 10);
    control.querySelector('[data-cantidad-restar]').disabled = cantidad <= 0;
    control.querySelector('[data-cantidad-sumar]').disabled = cantidad >= maximo;
}

function normalizarCantidad(input) {
    if (input.value === '') return null;
    const maximo = Number.parseInt(input.max, 10);
    let cantidad = Number.parseInt(input.value, 10);
    if (!Number.isFinite(cantidad)) cantidad = 0;
    cantidad = Math.max(0, Math.min(cantidad, maximo));
    input.value = cantidad;
    ajustarBotonesCantidad(input);
    return cantidad;
}

function prepararControlCantidad(input, alCambiar) {
    if (input.dataset.controlCantidadListo) return;
    input.dataset.controlCantidadListo = 'true';
    const control = input.closest('.pa-cantidad-control');
    ajustarBotonesCantidad(input);

    input.addEventListener('input', () => {
        if (normalizarCantidad(input) !== null) alCambiar(350);
    });
    input.addEventListener('change', () => {
        if (input.value !== '') return;
        input.value = '0';
        normalizarCantidad(input);
        alCambiar(0);
    });
    control.querySelector('[data-cantidad-restar]').addEventListener('click', () => {
        input.value = Math.max(0, Number.parseInt(input.value || '0', 10) - 1);
        ajustarBotonesCantidad(input);
        alCambiar(120);
    });
    control.querySelector('[data-cantidad-sumar]').addEventListener('click', () => {
        const maximo = Number.parseInt(input.max, 10);
        input.value = Math.min(maximo, Number.parseInt(input.value || '0', 10) + 1);
        ajustarBotonesCantidad(input);
        alCambiar(120);
    });
}

let colaActualizacionesCarrito = Promise.resolve();

function solicitarActualizacionCarrito(form, datos) {
    const ejecutar = async () => {
        const response = await fetch(form.action || location.href, {
            method: 'POST',
            body: datos,
            headers: {'X-Requested-With': 'XMLHttpRequest'},
        });
        if (!response.ok) throw new Error('HTTP');
        return new DOMParser().parseFromString(
            await response.text(), 'text/html'
        );
    };
    const solicitud = colaActualizacionesCarrito.then(ejecutar, ejecutar);
    colaActualizacionesCarrito = solicitud.catch(() => {});
    return solicitud;
}

function aplicarActualizacionCarrito(doc) {
    const nextPanel = doc.querySelector('[data-carrito-panel]');
    if (!nextPanel) throw new Error('Carrito no disponible');

    const currentMessages = document.querySelector('[data-mensajes]');
    const nextMessages = doc.querySelector('[data-mensajes]');
    if (currentMessages && nextMessages) currentMessages.replaceWith(nextMessages);

    const currentPanel = document.querySelector('[data-carrito-panel]');
    currentPanel.replaceWith(nextPanel);
    prepararCarrito(nextPanel);

    for (const form of document.querySelectorAll('[data-producto-carrito-form]')) {
        const nextForm = doc.querySelector(
            `[data-producto-carrito-form][data-producto-id="${form.dataset.productoId}"]`
        );
        if (!nextForm) continue;
        const input = form.querySelector('.pa-cantidad-valor');
        const nextInput = nextForm.querySelector('.pa-cantidad-valor');
        input.value = nextInput.value;
        input.max = nextInput.max;
        input.disabled = false;
        ajustarBotonesCantidad(input);
        form.removeAttribute('aria-busy');
    }
}

function prepararCarrito(panel = document) {
    const form = panel.querySelector('[data-carrito-form]');
    if (!form) return;
    const status = form.querySelector('[data-carrito-estado]');
    let timer;

    const sincronizar = async () => {
        clearTimeout(timer);
        const datos = new FormData(form);
        const controles = [...form.querySelectorAll('button, input[type="number"]')];
        controles.forEach(control => control.disabled = true);
        form.setAttribute('aria-busy', 'true');
        status.textContent = '';
        try {
            aplicarActualizacionCarrito(
                await solicitarActualizacionCarrito(form, datos)
            );
        } catch (error) {
            form.removeAttribute('aria-busy');
            form.querySelectorAll('.pa-cantidad-valor').forEach(input => {
                input.disabled = false;
                ajustarBotonesCantidad(input);
            });
            status.textContent = 'No se pudo actualizar la compra. Intenta nuevamente.';
        }
    };

    const programar = demora => {
        clearTimeout(timer);
        timer = setTimeout(sincronizar, demora);
    };
    form.querySelectorAll('.pa-cantidad-valor').forEach(input => {
        prepararControlCantidad(input, programar);
    });
    form.addEventListener('submit', event => {
        event.preventDefault();
        sincronizar();
    });
}

function prepararControlesProductos(contenedor = document) {
    for (const form of contenedor.querySelectorAll('[data-producto-carrito-form]')) {
        if (form.dataset.carritoListo) continue;
        form.dataset.carritoListo = 'true';
        const input = form.querySelector('.pa-cantidad-valor');
        const status = form.querySelector('[data-producto-carrito-estado]');
        let timer;

        const sincronizar = async () => {
            clearTimeout(timer);
            const datos = new FormData(form);
            const controles = [...form.querySelectorAll('button, input[type="number"]')];
            form.setAttribute('aria-busy', 'true');
            status.textContent = '';
            controles.forEach(control => control.disabled = true);
            try {
                aplicarActualizacionCarrito(
                    await solicitarActualizacionCarrito(form, datos)
                );
            } catch (error) {
                form.removeAttribute('aria-busy');
                input.disabled = false;
                ajustarBotonesCantidad(input);
                status.textContent = 'No se pudo actualizar. Intenta nuevamente.';
            }
        };

        const programar = demora => {
            clearTimeout(timer);
            timer = setTimeout(sincronizar, demora);
        };
        prepararControlCantidad(input, programar);
        form.addEventListener('submit', event => {
            event.preventDefault();
            sincronizar();
        });
    }
}

prepararCarrito();
prepararControlesProductos();
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
