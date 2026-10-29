# Análisis de entrega EVA 3 y de vendibilidad

**Fecha:** 28 de octubre de 2026
**Alcance:** software, documentación, diseño y evidencia frente a la rúbrica de la Unidad 3
(3.1.1 a 3.1.5), más evaluación comercial del producto.

## 1. Veredicto

| Pregunta | Respuesta |
|---|---|
| ¿El prototipo funciona? | **Sí.** Verificado hoy con stack real, modelo local, batería de 12 casos, prueba end-to-end y 194 pruebas automáticas |
| ¿Cumple la rúbrica EVA 3 completa? | **No todavía.** 3.1.1 y 3.1.3 están cubiertos con evidencia; **3.1.2 no**, porque falta la sesión con personas y los instrumentos de la unidad |
| ¿Se puede vender? | **Como piloto instalado en 1 o 2 hoteles, sí. Como SaaS autoservicio, no.** Faltan canal WhatsApp oficial, multiinquilino y validación del puente Beds24 |
| ¿El diseño es homogéneo? | **Parcial.** Landing y Chatwoot comparten paleta; panel y métricas la imitan con tokens duplicados y otra tipografía |

## 2. Qué se verificó en esta sesión

| Comprobación | Resultado |
|---|---|
| `make demo` (preflight) | 7/7 comprobaciones, modelo respondió en 36 s |
| `make e2e` (4 escenarios contra el stack real) | Todos los pasos PASS: FAQ, disponibilidad, fuera de turno, PMS caído, métricas, restauración |
| `make test` | 157 del copiloto + 25 del PMS simulado + 12 del puente Beds24 = **194 en verde** |
| Batería de 12 conversaciones | **11/12 (91,7%)**, sin fallos bloqueantes. El caso «argumentos de disponibilidad» falló en la corrida completa y pasó 3/3 al repetirlo aislado: es inestable bajo carga, no un defecto fijo |
| Stack | landing :8080, copiloto :8100, PMS :8200, Chatwoot :3000, todos `Up` |
| Landing en producción (sebita.dev) | Tarjeta del copiloto y casos de estudio ES/EN responden 200 |
| Panel de recepción | `/panel` responde 200 con login por cookie firmada |

## 3. Rúbrica EVA 3

Puntajes según la rúbrica entregada por la profesora: 15 + 20 + 15 + 20 + 30 = 100.

| Criterio | Peso | Estado | Evidencia | Brecha | Estimación |
|---|---|---|---|---|---|
| 3.1.1 Aplica fase de prototipado del Ciclo INACAP | 15 | Cubierto | Protección funcional demostrable en vivo; `docs/eva3/registro-de-iteraciones.md` §3 y §7 | Ninguna de fondo; explicar la etapa del ciclo en la presentación | 15/15 |
| 3.1.2 Prototipo testeado con usuarios en más de un ciclo | 20 | **No cubierto** | Solo hay prueba técnica (batería automática) | Falta sesión con personas reales (huéspedes y recepción), con registro de tarea, tiempo, dificultad y cambio sugerido. Faltan los instrumentos 3.1.2.1 storyboard, 3.1.2.2 mock-up, 3.1.2.3 ficha de planificación del testeo y 3.1.2.4 matriz CIM | 8-12/20 |
| 3.1.3 Ajusta el prototipo desde los resultados del testeo | 15 | Cubierto | Cinco iteraciones con hipótesis, fallo, causa y ajuste (`registro-de-iteraciones.md` §5); código y pruebas que lo respaldan | Falta sumar la iteración nacida de usuarios, no solo de la batería | 13-15/15 |
| 3.1.4 Verifica propuesta frente al estado del arte | 20 | Parcial | `docs/mercado.md` con siete fuentes citadas; PESTAL de EVA 1 | Falta la PESTAL profundizada de la unidad 3 y actualizar tendencias en el documento de entrega | 14-18/20 |
| 3.1.5 Justifica la pertinencia de la propuesta | 30 | Parcial-fuerte | Propuesta de valor EVA 2, métricas, costos y evidencia de mercado | Amarrar explícitamente al desafío de origen y al estado del arte en el mismo documento | 22-27/30 |

**Estimación honesta: 72 a 87 puntos.** El techo lo pone 3.1.2. Una sesión con usuarios, aunque sea
con compañeros de sección representando a huésped y recepción, sube la estimación a 90-100 y además
alimenta 3.1.3 con una iteración real.

## 4. Brechas académicas concretas

1. **Sesión con usuarios (bloqueante para 3.1.2).** `docs/piloto.md` ya tiene guion, hipótesis y
   métricas: sirve tal cual para la sesión, con la salvedad de que se hace con personas que
   representan roles, no con el hotel. Registrar por tarea: tiempo, errores, dificultad percibida y
   cambio sugerido.
2. **Instrumentos de la unidad 3 ausentes.** No existe en el repositorio ningún storyboard, mock-up,
   ficha de planificación del testeo, matriz CIM, panel de metáforas ni sus versiones iteradas.
3. **Números desactualizados en los documentos:**
   - `docs/eva3/registro-de-iteraciones.md:214` dice «136 casos»; hoy son 194.
   - `docs/escalabilidad.md:34` dice «139 casos del copiloto y 25 del PMS»; hoy son 157 + 25 + 12.
   - `docs/caso-de-estudio.md:84` dice «137 pruebas del copiloto · 25 del PMS».
   - `docs/escalabilidad.md:22` dice «Sin roles ni sesión: token en la URL del panel»; el panel ya
     tiene login con cookie firmada y nombre del autor de cada nota. Lo que falta son roles.
4. **No hay presentación EVA 3.** EVA 1 y EVA 2 tienen PPTX; esta entrega no. Si la profesora la
   pide, es un faltante tan visible como el código.
5. **Latencia y estabilidad:** en la corrida completa de hoy el modelo dio 25,8 s de mediana y
   118,7 s de p95, contra 17,7 s documentados y una meta de 10 s para FAQ. Un caso falló solo en esa
   corrida y pasó 3/3 aislado: la máquina comparte CPU con Docker y el modelo. Para la demo conviene
   cerrar contenedores que no se usan, mostrar el flujo guiado (0,3 s) y no prometer latencia de IA.

## 5. Producto: qué tan vendible es

### Fortalezas

- **Problema con evidencia:** 70% elige al negocio que responde primero (Moneypenny 2026); más de la
  mitad de los hoteles opera con dotación insuficiente (AHLA 2026). El segmento y las fuentes están
  en `docs/mercado.md`.
- **Diferenciación real:** código abierto, modelo local sin costo por consulta, derivación humana y
  lectura del PMS por contrato. Ningún competidor revisado combina las cuatro.
- **Guaridas de seguridad verificadas:** consentimiento comprobado sobre el texto del huésped, nombre
  con procedencia, guardrail de datos inventados, derivación determinista. La batería pasó de 9/12 a
  12/12 documentando cada fallo. Eso es lo que un hotel comprador quiere ver.
- **Operación de recepción resuelta:** cola por riesgo de SLA, resumen de turno, notas con autor,
  captura nocturna con etiqueta y nota privada fechada.
- **Costo verificable:** 90.000 CLP mensuales supuestos, sin costo por consulta.

### Lo que falta para vender

| Brecha | Por qué bloquea | Esfuerzo |
|---|---|---|
| WhatsApp oficial | El hotel vende por WhatsApp; el widget web no reemplaza el canal. Requiere proveedor (costo del cliente) | Medio |
| Validación real del puente Beds24 | Está construido y probado contra contrato, pero nunca contra una cuenta real | Bajo, cuando exista cuenta |
| Multiinquilino | Hoy es una instancia por hotel. Vendible como instalación, inviable como SaaS | Alto |
| Roles y auditoría | Cualquier sesión válida lo ve todo; falta separar recepción de gerencia | Bajo |
| Facturación y onboarding | No hay cobro, alta guiada ni migración de datos | Medio |
| Restauración de respaldos probada | Hay `make backup`; falta probar la restauración de punta a punta | Bajo |

**Conclusión comercial:** el producto es vendible hoy como **piloto pagado instalado** en un hotel
independiente de 10 a 40 habitaciones, con contrato de instalación, capacitación y soporte. No es
vendible como SaaS autoservicio hasta resolver multiinquilino y WhatsApp oficial.

## 6. Diseño

### Lo que está bien

- **Landing:** identidad propia y coherente. Serif editorial para títulos, Inter para texto, paleta
  cálida de hotel boutique, dispositivo de chat como pieza central y demo viva. Sigue el patrón de
  las mejores landings de producto conversacional revisadas en Mobbin (Beside, Agentcard, Wizz):
  demo interactiva en vez de capturas estáticas.
- **Tema oscuro completo** en landing y panel, con contraste corregido (Lighthouse 100 en las cuatro
  categorías, móvil y escritorio).
- **Chatwoot personalizado:** color del widget `#8C6A3F`, título y saludo del hotel
  (`infra/bootstrap/seed.rb:57-59`).

### Hallazgos con severidad

| Severidad | Hallazgo | Ubicación |
|---|---|---|
| Media | Tres paletas duplicadas con deriva: landing `--accent: #8d5a2b`, panel `#8c6a3f`, métricas `#8C6A3F` hardcodeado. Un cambio de marca obliga a editar tres archivos | `landing/demo.css:31`, `panel.html:10`, `metricas.html:9` |
| Media | Tres sistemas tipográficos distintos: instrument serif + Inter en landing, `system-ui` en panel, Georgia en métricas. El panel parece de otro producto | `demo.css:4-20`, `panel.html:18`, `metricas.html:13` |
| Media | El panel no tiene ancho máximo: abierto directo en escritorio, las tarjetas se estiran a todo el ancho | `panel.html:18` |
| Baja | Métricas no tiene tema oscuro; landing y panel sí | `metricas.html:9` |
| Baja | El panel está diseñado para la barra lateral de Chatwoot (correcto ahí), pero se usa también como página suelta en la demo | `panel.html` completo |

### Referencias Mobbin usadas

- Paneles operativos (Zillow, Airbnb anfitrión, Jobber, Navan): patrón lista + detalle + notas, con
  estado por color. El panel del copiloto respeta ese patrón dentro del ancho de Chatwoot.
- Landings de producto conversacional (Beside, Agentcard, Wizz, Revolut Support): demo viva y chat
  como protagonista. La landing del copiloto está alineada con ese patrón.

## 7. Plan priorizado

| # | Acción | Cierra | Tiempo |
|---|---|---|---|
| 1 | Sesión con 4-6 personas: 3 como huéspedes, 3 como recepción; guion de `docs/piloto.md`; registrar tarea, tiempo, dificultad y cambio sugerido | 3.1.2 y refuerza 3.1.3 | 1 día |
| 2 | Producir los instrumentos de la unidad 3 a partir de la sesión: storyboard, mock-up, ficha de testeo, matriz CIM y sus versiones iteradas | 3.1.2 y 3.1.3 | 1-2 días |
| 3 | Actualizar números y afirmaciones obsoletas y regenerar el DOCX de iteraciones | Coherencia de la entrega | 1 hora |
| 4 | Armar la presentación EVA 3 con la misma estructura de EVA 2 | Entrega completa | 1 día |
| 5 | Unificar tokens de diseño en un solo archivo y dar ancho máximo al panel | Diseño homogéneo | 2-3 horas |
| 6 | Validar Beds24 con cuenta real cuando exista | Vendibilidad | 1 hora |

## 8. Anexo: evidencia ejecutada hoy

```
make demo     7/7 comprobaciones · modelo qwen2.5-7b-instruct · primera respuesta 36 s
make e2e      PASS en FAQ, disponibilidad, fuera de turno, PMS caído, métricas y restauración
make test     157 + 25 + 12 = 194 pruebas en verde
batería       11/12 en corrida completa · caso fallido 3/3 al repetirlo aislado · p50 25,8 s · p95 118,7 s
```
