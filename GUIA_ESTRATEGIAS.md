# Guía Completa de Estrategias - Kraken Bot

Este documento detalla todas las estrategias de trading operativas en el sistema, incluyendo sus condiciones técnicas de entrada, gestión de riesgo (DCA) y lógica de cierre (Take Profit/Trailing Stop).

## Resumen Ejecutivo de Operación

| Estrategia | Tipo | Entrada Principal | Gestión en Caída (DCA) | Salida (TP / Trailing) |
| :--- | :--- | :--- | :--- | :--- |
| **Aggressive Sniper (S3)** | Sniper | VRel > 3, ERR > 2.5, RSI Extremo | No | ATR Trailing (Act 0.4%) |
| **AggrCent (S4)** | Scraper | VRel > 3, ERR > 2.5, RSI Extremo | No | Money Trailing (0.10€ -> 0.05€) |
| **HybridElite (S8)** | Sniper | RSI < 30, VRel > 3, Vela Verde, Stoch | No | Money Trailing (0.08€ -> 0.04€) |
| **RollingDCA (v1)** | DCA | RSI(5m) < 40 + Vela Verde | 3 Pasos fijos (-1.5%, -3%, -5%) | TP Fijo Neto +1.2% |
| **RollingDCA v2** | DCA | RSI(5m) < 40 + ADX/VRel | Granular: +1% caps cada 1% caída | TP 0.75% o TS (Act 1%, Dist 0.3%) |
| **RollingDCA v3** | DCA | RSI(5m) < 40 + ADX/VRel + Filtros | Smart: Distancia > 1.5% + Señal | TP Fijo Neto +1.0% |
| **Aspiradora PRO** | Sniper | RSI <= 12 o >= 88 + VRel/ADX | No | TS Extra Estrecho (Dist 0.1%) |
| **Hormiga / Grinder** | Sniper | RSI <= 15 o >= 85 + VRel | No | TS Extra Estrecho (Dist 0.1%) |
| **Saint-Grial Pro X3**| Maestro | RSI(5m) < 30 + Sniper | **25 Niveles (2/3 Cap)** | Trailing Dinámico (Act 0.6%, Dist 0.2%) |
| **Antigravity (A1)** | Sniper | RSI < 32, VRel > 1.5, Vela Verde | **25 Niveles (Rescate)** | TP 0.8% / Trailing (Act 0.5%, Dist 0.15%) |
| **VectorFlujo_V1** | Macro | EMA 200 (15m) + ADX > 20 | **15 Niveles (Búnker)** | Trailing Dinámico (Act 0.65%, Dist 0.15%) |

---

## Detalle de Estrategias

### 1. Familia Rolling DCA (Conservadoras / Acumulación)
Diseñadas para comprar en momentos de debilidad y promediar el precio si el mercado sigue cayendo.

*   **RollingDCA (v1):** Utiliza "pasos" fijos. Si el precio cae un 1.5%, compra un 50% más. Si cae otro 1.5%, compra el doble. Es la más robusta en mercados laterales.
*   **RollingDCA v2:** Es más reactiva. Inyecta pequeñas cantidades (1% del capital inicial) por cada 1% que baje el precio desde la entrada inicial. Incluye un Trailing Stop para dejar correr las ganancias si hay un rebote fuerte.
*   **RollingDCA v3 (Smart):** No promedia solo por precio. Espera a que haya una distancia mínima del 1.5% Y que los indicadores técnicos vuelvan a dar señal de compra.
*   **Rolling DCA Evolution (RDE):** La versión más avanzada de la familia. Incorpora filtros "Anti-Atrapamiento" (EMA 200 + ADX) y un sistema de DCA inteligente que espera a señales de sobreventa extrema (RSI 1m < 20) o Divergencias Alcistas de MFI antes de recomprar.
*   **RollingDCA Inmortal 50%:** Diseñada paraMEXC (0% comisiones). Cubre caídas del 50% mediante 25 niveles de recarga de 1.60€. Recalcula el Breakeven tras cada entrada para desplazar el siguiente nivel de DCA exactamente un 2% por debajo del nuevo promedio.

### 2. Familia Aggressive / Sniper (Rápidas / Alta Precisión)
Entran con un capital único y no promedian. Buscan movimientos explosivos (Momemtum).

*   **Aggressive Sniper (S3):** Busca "Climax" de volumen. Entra cuando el volumen relativo es enorme y el RSI está en extremos. Usa un **ATR Trailing Stop** que se va acercando al precio conforme pasa el tiempo para asegurar ganancias rápidamente.
*   **AggrCent (S4):** Optimización de la S3 para cuentas pequeñas. Su objetivo no es un porcentaje, sino ganar "céntimos" constantes (0.10€ brutos para asegurar 0.05€ netos).
## 1. Saint-Grial PRO X3 (Módulo Maestro Unificado)
La estrategia definitiva que sustituye y mejora a Kraken, Sentinel y RollingDCA. Diseñada para un capital base de 500€ con un protocolo unificado.

- **Capital & Apalancamiento:** 
    - Apalancamiento **x3 ISOLATED**.
    - Entrada inicial de **1/3 del capital** total (~166€).
    - **1 Solo Slot Activo** (Máxima concentración y eficiencia).
    - **Reserva Inmortal:** 2/3 del capital para gestionar caídas de hasta el 50% con 25 niveles de DCA.
- **Selector de Regímenes (El Cerebro):**
    - **Modo Halcón (Tendencia):** ADX > 25. Trailing Stop agresivo (Retroceso 0.15%) para exprimir la tendencia.
    - **Modo Aspiradora (Lateral):** ADX < 20. Trailing Stop rápido (Activación 0.40%) para capturar micro-movimientos.
    - **Modo Búnker (Pánico):** Caída > 3% en 15 min. Activa el protocolo de rescate de 25 niveles.
- **Lógica de Salida Pro-Hormiga:**
    - **Sin Stop Loss fijo:** Se busca siempre la recuperación mediante DCA.
    - **Filtro de Seguridad RSI:** No cierra posiciones si el RSI < 28 (esperando el rebote), a menos que el beneficio supere el 0.40% neto.
    - **Prohibición de Cierres en Negativo:** Bajo ninguna circunstancia se cierra una operación si el P&L neto es negativo.

## 2. Antigravity Sniper (A1)
La culminación de la seguridad y precisión. Combina un disparador ultra-selectivo con una defensa profunda de 25 niveles.
    -   **Entrada Sniper:** No entra por impulsividad. Requiere una coincidencia exacta de sobreventa (RSI < 32), inyección de interés institucional (VRel > 1.5) y una vela de confirmación alcista.
    -   **Muro de Contención:** Si el mercado cae, activa una red de 25 niveles de DCA cada -2%. Esto permite promediar posiciones hasta una caída total del -50%, asegurando que el precio medio esté siempre cerca del rebote inminente.
    -   **Salida de Alta Calidad:** Bloquea cierres basura. El Take Profit se busca al 0.80% con un Trailing Stop muy activo (0.15% callback) que solo se activa al llegar al 0.50% de beneficio neto.
    -   **Protocolo de Rescate:** Si la posición se complica y supera el nivel 3 de DCA, el sistema cambia a modo "Seguridad Máxima", ajustando el Trailing a 0.30% para salir en el primer respiro del mercado.

## 3. VectorFlujo_V1 (Dirección y Flujo Macro)
Módulo independiente diseñado para capitalizar las tendencias de largo plazo (15m) con una ejecución de alta precisión.
- **Filtro Macro Maestro:** Solo opera a favor de la **EMA 200 de 15 minutos**.
- **Filtro de Fuerza:** Solo entra si el **ADX > 20**, evitando mercados laterales y "trampas" de volumen.
- **Gestión Sniper:** Entrada concentrada (33% del capital) con apalancamiento **x3 Isolated**.
- **Defensa Búnker:** Reserva del 66% para **15 niveles de DCA**, ejecutados solo si la tendencia macro sigue siendo válida.
- **Cierre por Invalidez:** Cierre estructural inmediato si el precio cruza la EMA 200 en contra durante 2 velas de 5m, minimizando las pérdidas antes de que se conviertan en un problema.
- **Sandbox de Datos:** Registra su performance comparativa contra Hormiga y Sentinel para optimización continua.

---

## Glosario de Términos
*   **DCA (Dollar Cost Averaging):** Estrategia de comprar más cantidad a precios más bajos para reducir el coste promedio de la posición.
*   **VRel (Volumen Relativo):** Indica cuánto más volumen hay ahora comparado con la media. Un VRel > 3 significa que hay 3 veces más actividad de lo normal.
*   **ERR (Esfuerzo vs Resultado):** Mide si el volumen inyectado está moviendo el precio. Si hay mucho volumen pero el precio no se mueve, se espera un giro inminente.
*   **Trailing Stop:** Un stop loss que se mueve automáticamente a favor del beneficio una vez que se activa, protegiendo las ganancias acumuladas.
