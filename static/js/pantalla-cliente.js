const pantallaCliente = document.body;
const estadoUrl = pantallaCliente.dataset.estadoClienteUrl;
const tokenPantalla = location.hash.slice(1)
    || pantallaCliente.dataset.pantallaClienteToken;
if (location.hash) history.replaceState(null, '', location.pathname);
const espera = document.querySelector('[data-cliente-espera]');
const compra = document.querySelector('[data-cliente-compra]');
const productos = document.querySelector('[data-cliente-productos]');
const total = document.querySelector('[data-cliente-total]');
const estado = document.querySelector('[data-cliente-estado]');
const modalGracias = document.querySelector('[data-cliente-gracias]');
let ultimaVenta = pantallaCliente.dataset.ultimaVenta || '';
let temporizadorGracias;
const numeroClp = new Intl.NumberFormat('es-CL', {
    maximumFractionDigits: 0,
});
const formatearClp = valor => `$${numeroClp.format(valor)}`;

function actualizarPantalla(datos) {
    const tieneProductos = datos.productos.length > 0;
    espera.hidden = tieneProductos;
    compra.hidden = !tieneProductos;
    productos.replaceChildren();

    for (const producto of datos.productos) {
        const fila = document.createElement('tr');
        for (const [etiqueta, valor] of [
            ['Producto', producto.nombre],
            ['Cantidad', producto.cantidad],
            ['Precio unitario', formatearClp(producto.precio_unitario)],
            ['Total', formatearClp(producto.subtotal)],
        ]) {
            const celda = document.createElement('td');
            celda.dataset.label = etiqueta;
            celda.textContent = valor;
            fila.append(celda);
        }
        productos.append(fila);
    }
    total.textContent = formatearClp(datos.total);
    estado.textContent = '';

    const ventaConfirmada = String(datos.ultima_venta_id || '');
    if (ventaConfirmada && ventaConfirmada !== ultimaVenta) {
        ultimaVenta = ventaConfirmada;
        modalGracias.hidden = false;
        clearTimeout(temporizadorGracias);
        temporizadorGracias = setTimeout(() => {
            modalGracias.hidden = true;
        }, 5000);
    }
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
        estado.textContent = estado.dataset.mensajeReconexion;
    }
}

consultarEstado();
setInterval(consultarEstado, 1000);
