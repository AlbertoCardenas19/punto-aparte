const pantallaCliente = document.body;
const estadoUrl = pantallaCliente.dataset.estadoClienteUrl;
const tokenPantalla = location.hash.slice(1);
history.replaceState(null, '', location.pathname);
const espera = document.querySelector('[data-cliente-espera]');
const compra = document.querySelector('[data-cliente-compra]');
const productos = document.querySelector('[data-cliente-productos]');
const total = document.querySelector('[data-cliente-total]');
const estado = document.querySelector('[data-cliente-estado]');
const moneda = new Intl.NumberFormat('es-CL', {
    style: 'currency',
    currency: 'CLP',
    maximumFractionDigits: 0,
});

function actualizarPantalla(datos) {
    const tieneProductos = datos.productos.length > 0;
    espera.hidden = tieneProductos;
    compra.hidden = !tieneProductos;
    productos.replaceChildren();

    for (const producto of datos.productos) {
        const fila = document.createElement('tr');
        for (const valor of [
            producto.nombre,
            producto.cantidad,
            moneda.format(producto.precio_unitario),
            moneda.format(producto.subtotal),
        ]) {
            const celda = document.createElement('td');
            celda.textContent = valor;
            fila.append(celda);
        }
        productos.append(fila);
    }
    total.textContent = moneda.format(datos.total);
    estado.textContent = '';
}

async function consultarEstado() {
    try {
        const response = await fetch(estadoUrl, {
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'X-Pantalla-Cliente-Token': tokenPantalla,
            },
            cache: 'no-store',
        });
        if (!response.ok) throw new Error('HTTP');
        actualizarPantalla(await response.json());
    } catch (error) {
        estado.textContent = 'No se pudo actualizar la compra. Revisa la sesión de la caja.';
    }
}

consultarEstado();
setInterval(consultarEstado, 1000);
