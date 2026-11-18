# Auditoría y plan — 17 noviembre 2026

## Base examinada antes de implementar

Python/PyQt5 (única dependencia). Entrada `Ultimate Smasher.py`; interfaz QPainter
con widgets Qt en `smash_ui.py` (~3300 líneas); geometría del hub separada en
`hub_geometry.py`. `save_data.py` contiene offsets, modelo mutable, serialización,
backups y detección de Ryujinx. `gamepad.py` usa evdev; `sfx.py` sintetiza audio local.
Fuentes Barlow Condensed/Nunito/Font Awesome, retratos/renders/iconos locales;
licencias de retratos y fuentes incluidas. Arte central existente de uso privado.
Se conservan los cambios previos de esta sesión, sin commit ni despliegue.

## Diagnóstico priorizado

- P1: lectura no captura errores tras stat ni verifica longitud realmente leída.
- P1: no detecta modificaciones externas desde apertura. Un segundo slot puede
  fallar después de escribir el primero; no existe transacción atómica entre archivos.
- P1: índices de luchador negativos/fuera de tabla pueden escribir otros offsets.
- P2: backups parcialmente copiados pueden aparecer como restaurables; falta origen.
- P2: no existe undo/redo; las acciones masivas no informan cantidad/alcance.
- P2: roster fijo de 13 columnas comprime texto hasta7px; faltan búsqueda/filtros/scroll.
- P2: Items muestra iconos sin nombres; selección depende del hover/foco.
- P2: estado de edición acoplado a QObject dentro del archivo visual; tokens y estilos
  repetidos; animaciones reemplazadas se acumulan y no hay reducción de movimiento.
- P2: navegación pierde foco entre pantallas; algunos errores de backups no se capturan.
- P2: indicaciones de teclado dibujan simbología de mando aun sin mando conectado.

## Compatibilidad e integridad: evidencia y límites

El único layout identificado mide5982968bytes y usa offsets heredados de Ultimate
Smasher. El código original disponible en git también valida únicamente el tamaño;
no aporta un identificador fiable de versión ni algoritmo de checksum. No se
inventarán firmas, versiones compatibles ni checksums. Tamaño correcto no demuestra
compatibilidad: se indicará esta limitación en interfaz/documentación. La fuente
upstream consultada es https://github.com/Ret-HZ/Ultimate-Smasher (archivo original
local b930b89). Hay un save real local del tamaño esperado; las verificaciones de
escritura se harán exclusivamente en copias temporales, sin tocar los slots reales.

## Plan incremental

1. **Integridad**: validar lectura e índices; detectar conflictos externos; hacer
   backups completos recuperables, con metadata y fallos explícitos; pruebas de disco.
   Conservar offsets y todos los bytes desconocidos.
2. **Estado**: extraer Store, historial con deltas y transacciones recuperables;
   Ctrl+Z/Ctrl+Shift+Z, estado limpio vinculado al último guardado confirmado.
3. **Diseño compartido**: tokens, tipografía funcional legible, estados consistentes,
   reducción de movimiento y limpieza de animaciones; conservar lenguaje visual SSBU.
4. **Pantallas**: roster con búsqueda/filtros/scroll y acciones masivas explícitas;
   Items identificables y Max All confirmado/deshacible; General con contexto real;
   Backups con origen/errores; hub con tooltips/estado; foco recordado y ayudas claras.
5. **Respuesta y validación**: guardado fuera del hilo gráfico con bloqueo controlado
   de edición; suites de modelo/estado/UI y errores; copias del save real, capturas
   a distintas resoluciones y revisión del diff según ~/.codex/code_review.md.

Se mantendrán módulos visuales existentes donde extraerlos no aporte una mejora
segura; no se migrará de toolkit ni se introducirán recursos/dependencias externos.
