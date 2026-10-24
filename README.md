# ContaNext Guatemala

Aplicación Frappe de localización guatemalteca. Incluye modelos fiscales base y
contratos desacoplados para FEL. **No certifica DTE** hasta configurar e
implementar un adaptador de un certificador autorizado.

Incluye también la base técnica de libros contables: configuración por empresa,
roles separados, evidencias privadas, emisiones de borrador, diagnóstico de
catálogo y preflight contable. Los borradores de Diario, Mayor y Balance de
comprobación se generan en el worker `long`, se concilian entre sí y conservan
snapshot canónico particionado, manifiesto, CSV y XLSX como archivos privados.
El Libro de Estados Financieros agrega Balance General, Estado de Resultados y
anexos PDF privados previamente aprobados. Su revisión exige separación entre
preparador, revisor y aprobador, y conserva eventos inmutables de cada decisión.
El cierre técnico piloto produce un PDF privado, manifiesto, hashes y una reserva
símplex **simulada**, separada de la confirmación física de impresión. El estado
interno `Sealed` identifica el fin de esa simulación y no un sellado legal. Toda
salida permanece marcada como **NO AUTORIZADO — SOLO VALIDACIÓN TÉCNICA**; el
formato y consumo de folios legales continúan bloqueados hasta cerrar las
validaciones legales y profesionales documentadas.

La capa operativa detecta movimientos y cambios de maestros posteriores al
snapshot sin alterar emisiones selladas. También genera paquetes ZIP privados y
deterministas para requerimientos, limitados a empresa, período y emisiones
seleccionadas. Los soportes se indexan sin adjuntarlos por defecto; liberaciones
y descargas pasan por un endpoint auditado. Esto no reemplaza la revisión del
contador ni autoriza una entrega a SAT o al Registro Mercantil.

Para empresas existentes se incluye un diagnóstico `dry-run` determinista que
no modifica maestros, GL ni SLE. La línea base de upgrades queda fijada por un
contrato versionado; toda versión futura debe reejecutar las pruebas Frappe y de
aislamiento antes de aceptarse.

La app incluye además arneses de solo lectura para medir los pipelines de GL/SLE
y verificar, después de una restauración aislada, hashes, manifiestos, archivos
privados, cadenas de eventos y paquetes de requerimientos. Estas herramientas
producen evidencia técnica, pero no cierran G12 o G14 sin ejecución y acta
operativa sobre la infraestructura objetivo.
