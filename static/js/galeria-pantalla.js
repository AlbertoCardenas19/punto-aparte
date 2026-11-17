const galeria = document.querySelector('[data-galeria-pantalla]');
if (galeria) {
    const lista = galeria.querySelector('[data-galeria-lista]');
    const error = galeria.querySelector('[data-galeria-error]');
    const token = document.querySelector('[name="csrfmiddlewaretoken"]')?.value;
    const items = () => [...lista.querySelectorAll('[data-imagen-id]')];
    const ids = () => items().map(item => item.dataset.imagenId);
    let guardandoOrden = false;
    let arrastre = null;

    const mostrarError = texto => {
        error.textContent = texto;
        error.hidden = !texto;
    };
    const restaurar = orden => {
        const porId = new Map(items().map(item => [item.dataset.imagenId, item]));
        orden.forEach(id => lista.append(porId.get(id)));
    };
    const enviar = async datos => {
        datos.set('csrfmiddlewaretoken', token);
        const respuesta = await fetch(galeria.dataset.url, {
            method: 'POST', body: datos, headers: {'X-Requested-With': 'XMLHttpRequest'},
        });
        if (!respuesta.ok) throw new Error('No se pudo guardar');
        return respuesta.json();
    };
    const guardarOrden = async anterior => {
        if (guardandoOrden || ids().join(',') === anterior.join(',')) return;
        guardandoOrden = true;
        mostrarError('');
        const datos = new FormData();
        datos.set('accion', 'ordenar');
        ids().forEach(id => datos.append('imagen_id', id));
        try {
            const resultado = await enviar(datos);
            if (resultado.orden.join(',') !== ids().join(',')) throw new Error('Orden inesperado');
        } catch {
            restaurar(anterior);
            mostrarError('No se pudo guardar el orden. Se restauró el anterior.');
        } finally {
            guardandoOrden = false;
        }
    };

    lista.addEventListener('click', event => {
        const boton = event.target.closest('[data-mover]');
        if (!boton || guardandoOrden) return;
        const item = boton.closest('[data-imagen-id]');
        const anterior = ids();
        const indice = items().indexOf(item);
        const direccion = Number(boton.dataset.mover);
        const vecino = items()[indice + direccion];
        if (!vecino) return;
        if (direccion < 0) lista.insertBefore(item, vecino);
        else lista.insertBefore(vecino, item);
        boton.focus();
        guardarOrden(anterior);
    });
    lista.addEventListener('pointerdown', event => {
        const asa = event.target.closest('[data-arrastrar]');
        if (!asa || guardandoOrden || event.button !== 0) return;
        event.preventDefault();
        const item = asa.closest('[data-imagen-id]');
        arrastre = {item, asa, anterior: ids(), pointerId: event.pointerId};
        asa.setPointerCapture(event.pointerId);
        item.classList.add('pa-galeria-arrastrando');
    });
    document.addEventListener('pointermove', event => {
        if (!arrastre || arrastre.pointerId !== event.pointerId) return;
        const destino = document.elementFromPoint(event.clientX, event.clientY)
            ?.closest('[data-imagen-id]');
        if (!destino || destino === arrastre.item || destino.parentElement !== lista) return;
        const origen = items().indexOf(arrastre.item);
        const posicion = items().indexOf(destino);
        lista.insertBefore(arrastre.item, posicion > origen ? destino.nextSibling : destino);
    });
    const terminar = event => {
        if (!arrastre || arrastre.pointerId !== event.pointerId) return;
        arrastre.item.classList.remove('pa-galeria-arrastrando');
        const anterior = arrastre.anterior;
        arrastre = null;
        if (event.type === 'pointercancel') restaurar(anterior);
        else guardarOrden(anterior);
    };
    document.addEventListener('pointerup', terminar);
    document.addEventListener('pointercancel', terminar);

    lista.addEventListener('change', async event => {
        const interruptor = event.target.closest('[data-imagen-activa]');
        if (!interruptor) return;
        const nuevoEstado = interruptor.checked;
        interruptor.disabled = true;
        mostrarError('');
        const datos = new FormData();
        datos.set('accion', 'estado');
        datos.set('imagen_id', interruptor.closest('[data-imagen-id]').dataset.imagenId);
        datos.set('activa', nuevoEstado ? '1' : '0');
        try {
            const resultado = await enviar(datos);
            if (resultado.activa !== nuevoEstado) throw new Error('Estado inesperado');
        } catch {
            interruptor.checked = !nuevoEstado;
            mostrarError('No se pudo guardar el interruptor. Se restauró su estado anterior.');
        } finally {
            interruptor.disabled = false;
        }
    });
}
