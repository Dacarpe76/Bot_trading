# Estrategias Activas del Bot Principal

Este documento detalla todas las estrategias de trading que están actualmente instanciadas y funcionando en el bot principal (`kraken_bot`).

## 1. Aggressive (y Variantes Long/Short)
**Clase:** `StrategyAggressive`  
**Instancias:** `Aggressive` (Mixed), `Aggressive_L` (Solo Long), `Aggressive_S` (Solo Short).

### Descripción
Estrategia de momentum y reversión agresiva basada en volumen relativo (VRel) y Ratio Esfuerzo/Resultado (ERR). Incluye una modalidad de "Momentum" para capturar caídas fuertes en Short.

### Lógica de Entrada (Entry)
1.  **Estándar (S3 Logic):**
    *   **Volumen Relativo (VRel):** > 3.0
    *   **Esfuerzo/Resultado (ERR):** > 2.5
    *   **RSI:** Long si RSI < 40 | Short si RSI > 60.
    *   **Filtro:** Bloquea Longs si la Tendencia Global es "DUMP".
2.  **Climax (Extremo):**
    *   **VRel:** > 10.0
    *   **RSI:** Long si RSI < 15 | Short si RSI > 85.
3.  **Momentum Short (Prioritario):**
    *   Precio < Banda de Bollinger Inferior.
    *   **MFI:** < 15 (Dinero saliendo).
    *   **ADX:** > 25 (Tendencia fuerte).

### Lógica de Salida (Exit)
*   **Trailing Stop Estándar:** Basado en ATR (Multiplicador 3.0). Se activa tras > 0.4% de beneficio. Incluye decaimiento por tiempo (acerca el stop 0.1 ATR cada 10 min).
*   **Momentum Mode:** Trailing Stop dinámico del 0.8% desde el precio más bajo alcanzado.
*   **Límites de Tiempo:**
    *   > 4 Horas: Cierra si Beneficio Neto >= 0.01€.
    *   > 8 Horas: Cierra si Pérdida Neta >= -0.05€ (Corte de perdidas por tiempo).

---

## 2. AggrCent (y Variantes Long/Short)
**Clase:** `StrategyAggressiveCent`  
**Instancias:** `AggrCent` (Mixed), `AggrCent_L` (Long), `AggrCent_S` (Short).

### Descripción
Variación de la estrategia Aggressive enfocada en micro-beneficios absolutos en Euros ("Céntimos"). Ideal para acumulación constante con alta tasa de aciertos.

### Lógica de Entrada
*   Idéntica a la **Lógica Estándar y Climax** de `Aggressive`.
*   (Nota: No utiliza la lógica específica de "Momentum Short" de la S3).

### Lógica de Salida (Exit - Basada en Valor Monetario)
*   **Activación:** Beneficio Neto >= **0.10 €**.
*   **Preservación:** Al activar, coloca Stop Loss para asegurar **0.05 €** de ganancia.
*   **Step (Escalera):** Por cada **0.01 €** extra de ganancia, asegura **0.01 €** más.
*   **Regla de Inactividad:** Si el precio no mueve el stop en 5 minutos, el stop se mueve 0.01€/unidad de activo a favor del cierre (fuerza el cierre gradualmente).
*   **Límites de Tiempo:** 1 Hora (+0.01€) / 2 Horas (>-0.05€).

---

## 3. NetScalp (NetScalpDCA)
**Clase:** `StrategyNetScalpDCA`  
**Instancias:** `NetScalp`

### Descripción
Estrategia de "Buy the Dip" (Compra en caídas) puramente técnica con red de seguridad (DCA). Busca rebotes rápidos en sobreventa extrema.

### Lógica de Entrada (Solo LONG)
1.  **RSI:** < 30 (Sobreventa fuerte).
2.  **Confirmación:** Cierre de vela de 1m > Alto de la vela anterior (Patrón de giro alcista).

### Lógica de Salida
*   **Objetivo Fijo:** Busca un Beneficio Neto de **0.05 €**.
*   **Trailing:** Se activa al llegar a 0.05€. Stop inicial en 0.04€. Distancia de trailing: 0.01€.

### Gestión de Riesgo (DCA - Safety Orders)
*   **Disparo:** Si el precio cae un **1.5%** desde la última entrada.
*   **Max DCA:** Hasta 3 compras adicionales para promediar el precio de entrada.

---

## 4. SniperShort
**Clase:** `StrategySniperShort`  
**Instancias:** `SniperShort` (Capital Dedicado: 500€)

### Descripción
Estrategia quirúrgica de venta en corto (Short) buscando "Blow-off Tops" (techos de mercado eufóricos).

### Lógica de Entrada (Solo SHORT)
1.  **RSI:** > 75 (Sobrecompra Extrema).
    *   *Adaptativo:* Si Tendencia="DUMP", baja el requisito a RSI > 60.
2.  **ADX:** > 43 (Tendencia agotada o muy extendida).

### Lógica de Salida
*   **Trailing Stop:** Estándar (ATR x 3.0), Activación > 0.4%.
*   **Límites de Tiempo:** 4 Horas (+0.01€) / 8 Horas (>-0.05€).

---

## 5. HybridElite
**Clase:** `StrategyHybridElite`  
**Instancias:** `HybridElite` (Capital Dedicado: 500€)

### Descripción
Combina la entrada técnica de Aggressive (refinada) con la salida segura de "Céntimos" de AggrCent. Evita entrar en "cuchillos cayendo".

### Lógica de Entrada
1.  **Filtros Base:** VRel > 3.0, ERR > 2.5.
2.  **RSI Estricto:** Long < 30 | Short > 60.
    *   *Adaptativo:* Si ADX > 40 (Tendencia fuerte en contra), exige RSI < 20 para Long.
    *   *Trend:* Bloquea Longs si Global Trend es "DUMP".
3.  **Confirmaciones (Anti-Trampa):**
    *   **Vela Verde:** Precio actual > Precio de Apertura (evita entrar en vela roja cayendo).
    *   **Stoch:** K > D (Momentum girando).

### Lógica de Salida
*   **Tipo:** "Cent Scraper" (Igual a AggrCent).
*   **Parámetros:** Activa en **0.08 €**, Asegura **0.04 €**. Step 0.01€.

---

## 6. RollingDCA
**Clase:** `StrategyRollingDCA`  
**Instancias:** `RollingDCA` (Capital Dedicado: 1000€)

### Descripción
Estrategia de acumulación pasiva ("Peace of Mind"). Compra en debilidad relativa y promedia a la baja agresivamente si el mercado cae.

### Lógica de Entrada (Solo LONG)
1.  **RSI (5 min):** < 40.
2.  **Límite:** Máximo 3 posiciones simultáneas.
3.  **Filtro:** No entra si la vela actual es roja (Precio <= Open).

### Lógica de Salida
*   **Take Profit:** Precio Promedio + **1.2%**.

### Red de Seguridad (Martingala/DCA)
*   **Paso 1:** Caída -1.5% -> Compra x1.5 tamaño base.
*   **Paso 2:** Caída -3.0% (total) -> Compra x2.0 tamaño base.
*   **Paso 3:** Caída -5.0% (total) -> Compra x3.0 tamaño base.
