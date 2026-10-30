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

document.addEventListener('show.bs.modal', event => {
    if (event.target.id !== 'modal-detalle-producto') return;
    const trigger = event.relatedTarget;
    if (!trigger?.matches('[data-producto-detalle]')) return;
    const modal = event.target;
    modal.querySelector('[data-detalle-nombre]').textContent = trigger.dataset.productoNombre;
    modal.querySelector('[data-detalle-marca]').textContent = trigger.dataset.productoMarca;
    modal.querySelector('[data-detalle-categorias]').textContent = trigger.dataset.productoCategorias;
    modal.querySelector('[data-detalle-codigo]').textContent = trigger.dataset.productoCodigo;
    modal.querySelector('[data-detalle-descripcion]').textContent = trigger.dataset.productoDescripcion;
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

function reemplazarResultadosBusqueda(doc, url) {
    const results = document.querySelector('[data-resultados-busqueda]');
    const next = doc.querySelector('[data-resultados-busqueda]');
    if (!results || !next) throw new Error('Resultados no disponibles');
    for (const [toggle, entry] of menus) {
        bootstrap.Dropdown.getInstance(toggle)?.hide();
        entry.menu.remove();
        menus.delete(toggle);
    }
    results.replaceWith(next);
    prepararBotonesAgregar(next);
    history.replaceState(null, '', url);
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
            url.search = new URLSearchParams({q: input.value}).toString();
            const results = document.querySelector('[data-resultados-busqueda]');
            results.setAttribute('aria-busy', 'true');
            status.textContent = 'Buscando…';
            try {
                const response = await fetch(url, {signal: controller.signal});
                if (!response.ok) throw new Error('HTTP');
                const doc = new DOMParser().parseFromString(
                    await response.text(), 'text/html'
                );
                if (current !== version) return;
                reemplazarResultadosBusqueda(doc, url);
                status.textContent = '';
            } catch (error) {
                if (current === version && error.name !== 'AbortError') {
                    status.textContent = 'No se pudo actualizar. Usa Buscar para intentarlo nuevamente.';
                }
            } finally {
                if (current === version) {
                    document.querySelector('[data-resultados-busqueda]')
                        .removeAttribute('aria-busy');
                }
            }
        }, 300);
    });

    input.addEventListener('keydown', async event => {
        if (event.key !== 'Enter' || !input.value.trim()) return;
        event.preventDefault();
        clearTimeout(timer);
        controller?.abort();
        ++version;
        const url = new URL(form.action || location.href);
        url.search = new URLSearchParams({q: input.value.trim()}).toString();
        const token = document.querySelector('[name="csrfmiddlewaretoken"]')?.value;
        if (!token) {
            location.assign(url);
            return;
        }
        const datos = new FormData();
        datos.append('csrfmiddlewaretoken', token);
        datos.append('accion', 'escanear');
        datos.append('codigo', input.value.trim());
        status.textContent = 'Buscando…';
        try {
            const response = await fetch(url, {
                method: 'POST',
                body: datos,
                headers: {'X-Requested-With': 'XMLHttpRequest'},
            });
            if (!response.ok) throw new Error('HTTP');
            const doc = new DOMParser().parseFromString(
                await response.text(), 'text/html'
            );
            reemplazarResultadosBusqueda(doc, url);
            if (response.headers.get('X-Codigo-Encontrado') === '1') {
                aplicarActualizacionCarrito(doc);
            }
            status.textContent = '';
        } catch (error) {
            status.textContent = 'No se pudo buscar. Usa el botón Buscar para intentarlo nuevamente.';
        }
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

function trasladarErroresAlEstado(doc, selectorEstado) {
    const errores = [...doc.querySelectorAll('[data-mensajes] [role="alert"]')]
        .map(error => error.textContent.trim())
        .filter(Boolean);
    if (!errores.length) return;
    const status = doc.querySelector(selectorEstado);
    if (status) {
        status.textContent = errores.join(' ');
        status.classList.add('pa-estado-error');
    }
    doc.querySelector('[data-mensajes]')?.replaceChildren();
}

function aplicarActualizacionCarrito(doc) {
    const nextPanel = doc.querySelector('[data-carrito-panel]');
    if (!nextPanel) throw new Error('Carrito no disponible');

    const currentMessages = document.querySelector('[data-mensajes]');
    const nextMessages = doc.querySelector('[data-mensajes]');
    if (currentMessages && nextMessages) currentMessages.replaceWith(nextMessages);

    const modales = ['modal-cobro', 'modal-vaciar-venta'].map(id => {
        const modal = doc.querySelector(`#${id}`);
        modal?.remove();
        document.querySelector(`#${id}`)?.remove();
        return modal;
    });

    const currentPanel = document.querySelector('[data-carrito-panel]');
    currentPanel.replaceWith(nextPanel);
    prepararCarrito(nextPanel);
    modales.forEach(modal => {
        if (modal) document.body.append(modal);
    });

    const currentMobileTotal = document.querySelector('[data-total-carrito-movil]');
    const nextMobileTotal = doc.querySelector('[data-total-carrito-movil]');
    if (currentMobileTotal && nextMobileTotal) {
        currentMobileTotal.textContent = nextMobileTotal.textContent;
    }

    for (const card of [...document.querySelectorAll('[data-producto-tarjeta]')]) {
        const nextCard = doc.querySelector(
            `[data-producto-tarjeta][data-producto-id="${card.dataset.productoId}"]`
        );
        if (!nextCard) continue;
        card.replaceWith(nextCard);
        prepararBotonesAgregar(nextCard);
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
        status.classList.remove('pa-estado-error');
        try {
            const doc = await solicitarActualizacionCarrito(form, datos);
            trasladarErroresAlEstado(doc, '[data-carrito-estado]');
            aplicarActualizacionCarrito(doc);
        } catch (error) {
            form.removeAttribute('aria-busy');
            form.querySelectorAll('.pa-cantidad-valor').forEach(input => {
                input.disabled = false;
                ajustarBotonesCantidad(input);
            });
            status.textContent = 'No se pudo actualizar la compra. Intenta nuevamente.';
            status.classList.add('pa-estado-error');
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

function prepararBotonesAgregar(contenedor = document) {
    for (const form of contenedor.querySelectorAll('[data-agregar-producto]')) {
        if (form.dataset.agregarListo) continue;
        form.dataset.agregarListo = 'true';
        const status = form.querySelector('[data-agregar-estado]');
        form.addEventListener('submit', async event => {
            event.preventDefault();
            const datos = new FormData(form);
            const button = form.querySelector('button[type="submit"]');
            form.setAttribute('aria-busy', 'true');
            status.textContent = '';
            status.classList.remove('pa-estado-error');
            button.disabled = true;
            try {
                const productoId = datos.get('producto_id');
                const doc = await solicitarActualizacionCarrito(form, datos);
                trasladarErroresAlEstado(
                    doc,
                    `[data-producto-tarjeta][data-producto-id="${productoId}"] [data-agregar-estado]`
                );
                aplicarActualizacionCarrito(doc);
            } catch (error) {
                form.removeAttribute('aria-busy');
                button.disabled = false;
                status.textContent = 'No se pudo agregar. Intenta nuevamente.';
                status.classList.add('pa-estado-error');
            }
        });
    }
}

prepararCarrito();
prepararBotonesAgregar();
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
