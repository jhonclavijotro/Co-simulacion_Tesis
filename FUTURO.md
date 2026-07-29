# FUTURO: Próximos Pasos — Co-simulación Multiagente

## Prioridad Alta: Pendientes P3–P8 (Post-auditoría BESS)

### P3 — Controlador PI con Anti-Windup en BuckBoost
Archivo: `BESS/BuckBoost.py`

- [ ] Reemplazar el PI actual del lazo de corriente por uno con anti-windup por saturación condicional (conditional integration)
- [ ] Límites de saturación del duty cycle: `[d_min, d_max]` configurables
- [ ] Test: seguimiento de `I_bat_ref` con error estacionario nulo en regimen permanente
- [ ] Test: sin overshoot en saturación tras escalón de `I_bat_ref`

### P4 — Límite de Corriente del Inversor
Archivo: `BESS/SistemaBESS.py`

- [ ] Hacer `I_inv_max` configurable desde `__init__` (actualmente 50A fijo)
- [ ] Implementar limitación de corriente en modo detallado (hoy solo existe en promedio)
- [ ] Implementar limitación dinámica: reducir `I_inv_max` cuando `V_pcc < 0.85 pu`
- [ ] Probar respuesta a hueco de tensión (voltage sag) con `V_pcc = 0.7 pu`

### P5 — Eficiencia Round-Trip en Modelo Simplificado
Archivo: `MAS/BESS_simplificado.py`

- [ ] Agregar `eta_charge` y `eta_discharge` como parámetros del `__init__`
- [ ] Aplicar eficiencia: `P_real = P_ref * eta` (carga: `eta=eta_charge`, descarga: `eta=eta_discharge`)
- [ ] Valor por defecto: `eta_charge = 0.92`, `eta_discharge = 0.95` (Li-ion típico)
- [ ] Test: energía extraída > energía almacenada en un ciclo completo carga/descarga

### P6 — BuckBoost PI Mejorado (Refinamiento)
Archivo: `BESS/BuckBoost.py`

- [ ] Sintonizar ganancias `Kp`, `Ki` mediante Ziegler-Nichols o asignación de polos
- [ ] Agregar feedforward de `I_bat_ref` para mejorar respuesta transitoria
- [ ] Agregar modo boost (elevador) separado del modo buck (reductor)
- [ ] Test: conmutación buck-boost sin discontinuidad en la corriente

### P7 — Protocolo de Dinámica Remota (Extensión)
Archivo: `Dinamica/servicio_dinamica.py`

- [ ] Agregar soporte para `V_pcc` en el comando `step()` del servicio
- [ ] Extender `ClienteDinamica.step()` con parámetro `V_pcc` opcional
- [ ] Agregar comando `set_param` para cambiar parámetros en caliente (`eta`, `I_inv_max`, etc.)
- [ ] Test: step remoto con V_pcc y verificar que SoC cambia correctamente

### P8 — Documentación en Obsidian
Vault: `D:\PERSONAL\obsidian\cerebro\`

- [ ] Crear nota `Tesis-Arquitectura-BESS.md` con diagrama de bloques y ecuaciones del BuckBoost + Batería
- [ ] Crear nota `Tesis-Plan-P3-P8.md` con estado de cada mejora y resultados de tests
- [ ] Actualizar `Tesis-Fuente-Corriente-Equivalente.md` si quedaron ecuaciones pendientes
- [ ] Vincular todas las notas con wikilinks bidireccionales

---

---

# FUTURO: Base de Datos de Paneles Solares y Clima Via MQTT (Original)

## 1. Correcciones a la Vision Inicial

Dos correcciones fundamentales a la primera version de este documento:

1. **Rs, Rsh, n no se almacenan, se extraen.** Las fichas tecnicas rara vez incluyen estos valores. El catalogo contiene solo datos crudos del datasheet (Voc, Isc, Vmp, Imp, Pmax, Ki, Kv, NOCT, Ns). Rs, Rsh, n se calculan mediante algoritmos de extraccion al cargar el panel.

2. **El clima llega por MQTT, no es constante ni se lee de archivo.** Ambos sistemas (actual y futuro) deben recibir perfiles meteorologicos via MQTT antes de la simulacion. Esto implica un componente MQTT que recibe y almacena en buffer los datos, y la simulacion los consume paso a paso.

---

## 2. Arquitectura del Sistema con MQTT

### 2.1 Flujo de Datos General

```
┌──────────────┐     MQTT      ┌──────────────────────┐
│ Fuente       │──────────────>│   ClienteMQTT        │
│ Clima        │  topics:      │                      │
│ (BESS + PV)  │  clima/poa    │  - Buffer circular   │
│              │  clima/temp   │    de datos climaticos│
│              │  clima/wind   │  - Sincronizacion     │
│              │  clima/tiempo │  - Timestamps         │
└──────────────┘              └──────┬───────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────┐
│                   Simulacion                        │
│                                                     │
│  ┌──────────┐   ┌──────────┐   ┌───────────────┐  │
│  │          │   │          │   │               │  │
│  │ Solar    │──>│ MPPT     │──>│ Boost         │  │
│  │ Panel(s) │   │ Controller│   │ Converter     │  │
│  │          │   │          │   │               │  │
│  └──────────┘   └──────────┘   └───────┬───────┘  │
│                                        │           │
│  ┌──────────┐   ┌──────────┐           │           │
│  │          │   │          │           │           │
│  │ BESS     │<──│ DC Bus   │<──────────┘           │
│  │ Battery  │   │ 400V     │                       │
│  │          │   │          │──> Inversor → Red     │
│  └──────────┘   └──────────┘                       │
└────────────────────────────────────────────────────┘
        ↑
        │ Consume cada paso
        └── ClienteMQTT.buffer
```

### 2.2 Componentes Nuevos

#### 2.2.1 ClienteMQTT

Componente que se conecta al broker MQTT y recibe datos meteorologicos en tiempo real.

```python
class ClienteMQTT:
    """
    Suscriptor MQTT que acumula datos climaticos en un buffer
    para ser consumidos por la simulacion paso a paso.
    """
    def __init__(self, broker_host, broker_port=1883,
                 topic_poa="clima/poa",
                 topic_temp="clima/temp",
                 topic_wind="clima/wind",
                 topic_time="clima/tiempo",
                 buffer_size=86400):  # 24h a 1s
        self.buffer = {
            "tiempo": [],   # timestamps (int)
            "poa": [],      # irradiancia [W/m2]
            "temp": [],     # temperatura ambiente [°C o K]
            "wind": []      # velocidad viento [m/s]
        }
        self.buffer_size = buffer_size
        self._indice = 0        # indice de lectura actual
        self._conectado = False
        self._cargando = True   # True mientras recibe datos
        self._init_mqtt(broker_host, broker_port, topics)

    def _init_mqtt(self, host, port, topics):
        """Configura callbacks MQTT para cada topic."""
        self.client = mqtt.Client()
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.connect(host, port)
        self.client.loop_start()

    def _on_message(self, client, userdata, msg):
        """Acumula cada mensaje en el buffer correspondiente."""
        topic = msg.topic
        valor = float(msg.payload.decode())
        if topic.endswith("poa"):
            self.buffer["poa"].append(valor)
        elif topic.endswith("temp"):
            self.buffer["temp"].append(valor)
        elif topic.endswith("wind"):
            self.buffer["wind"].append(valor)
        elif topic.endswith("tiempo"):
            self.buffer["tiempo"].append(int(valor))
        # Control de tamano del buffer FIFO
        if len(self.buffer["poa"]) > self.buffer_size:
            for k in self.buffer:
                self.buffer[k].pop(0)

    @property
    def completado(self):
        """True cuando se recibieron todos los datos."""
        return not self._cargando

    def iniciar_carga(self):
        """Espera hasta que el buffer tenga datos."""
        self._cargando = True
        print("Esperando datos climaticos via MQTT...")

    def detener_carga(self):
        """Marca la carga como completa."""
        self._cargando = False
        self._indice = 0
        print(f"Clima cargado: {len(self.buffer['tiempo'])} pasos.")

    def leer_siguiente_paso(self):
        """Retorna (poa, temp, wind) para el paso actual."""
        if self._indice >= len(self.buffer["poa"]):
            return None  # simulacion completa
        paso = (
            self.buffer["poa"][self._indice],
            self.buffer["temp"][self._indice],
            self.buffer["wind"][self._indice]
        )
        self._indice += 1
        return paso

    def limpiar_buffer(self):
        """Limpia el buffer para una nueva simulacion."""
        for k in self.buffer:
            self.buffer[k].clear()
        self._indice = 0

    def desconectar(self):
        self.client.loop_stop()
        self.client.disconnect()
```

#### 2.2.2 PanelDatabase (Redisenada)

Ahora con extraccion automatica de Rs, Rsh, n desde datos crudos del datasheet.

```python
class PanelDatabase:
    """
    Catalogo de paneles solares. Almacena solo datos crudos del datasheet.
    Rs, Rsh, n se extraen automaticamente al crear un SolarPanel.
    """
    def __init__(self, archivo="data/paneles/catalogo.json"):
        self.archivo = archivo
        self.paneles: dict[str, dict] = {}
        self.cargar()

    def cargar(self):
        """Carga catalogo desde JSON. Sin extraccion, solo datos crudos."""
        with open(self.archivo, "r", encoding="utf-8") as f:
            data = json.load(f)
        for p in data["paneles"]:
            self.paneles[p["modelo"]] = p

    def obtener(self, modelo: str) -> dict:
        """Retorna datos crudos del datasheet (sin Rs, Rsh, n)."""
        if modelo not in self.paneles:
            raise KeyError(f"Panel '{modelo}' no encontrado.")
        return self.paneles[modelo]

    def crear_panel(self, modelo: str, **kwargs) -> "SolarPanel":
        """
        Crea SolarPanel: extrae Rs, Rsh, n desde datos crudos.
        kwargs sobreescriben parametros extraidos (ej: n=1.3).
        """
        raw = self.obtener(modelo)
        # Extraer Rs, Rsh, n desde datos del datasheet
        extraidos = extraer_parametros(
            voc=raw["stc"]["voc"],
            isc=raw["stc"]["isc"],
            vmp=raw["stc"]["vmp"],
            imp=raw["stc"]["imp"],
            pmax=raw["stc"]["pmax"],
            ki=raw["coeficientes"]["ki"],
            kv=raw["coeficientes"]["kv"],
            ns=raw["fisico"]["ns"]
        )
        extraidos.update(kwargs)  # sobreescribir manualmente si se desea
        params = {**raw, **extraidos}
        return SolarPanel(params)

    @staticmethod
    def agregar_desde_datasheet(stc: dict, coeficientes: dict,
                                 fisico: dict, fabricante: str,
                                 modelo: str, tecnologia: str = ""):
        """
        Crea una entrada para el catalogo con SOLO datos crudos.
        Rs, Rsh, n se extraeran al crear el panel, no se almacenan.
        """
        return {
            "fabricante": fabricante,
            "modelo": modelo,
            "tecnologia": tecnologia,
            "stc": stc,
            "coeficientes": coeficientes,
            "fisico": fisico
        }
```

#### 2.2.3 Extraccion de Parametros (Nuevo modulo)

```python
def extraer_parametros(voc, isc, vmp, imp, pmax, ki, kv, ns=60,
                       metodo="villalva"):
    """
    Estima Rs, Rsh, n a partir de datos tipicos del datasheet.
    No requiere que el datasheet incluya estos valores.
    
    Parametros de entrada (SIEMPRE disponibles en cualquier datasheet):
      voc, isc, vmp, imp, pmax, ki, kv, ns
    
    Parametros de salida (NUNCA en datasheet, siempre extraidos):
      Rs, Rsh, n
    """
    if metodo == "villalva":
        return _extraer_villalva(voc, isc, vmp, imp, pmax, ki, kv, ns)
    elif metodo == "analitico":
        return _extraer_analitico(voc, isc, vmp, imp, pmax, ki, kv, ns)
    else:
        raise ValueError(f"Metodo '{metodo}' no soportado.")

def _extraer_villalva(voc, isc, vmp, imp, pmax, ki, kv, ns):
    """
    Metodo de Villalva et al. 2009:
    - Asume n inicial (~1.2)
    - Estima Rsh desde pendiente cerca de Isc
    - Estima Rs desde pendiente cerca de Voc
    - Itera para ajustar Pmax_calculado = Pmax_datasheet
    """
    Vt = ns * 1.38e-23 * 298.15 / 1.6e-19  # Vt a STC
    
    # Paso 1: n inicial tipico segun tecnologia
    n = 1.2
    
    # Paso 2: Rsh inicial (pendiente cerca de Isc)
    Rsh = voc / (isc * 0.01)
    
    # Paso 3: Rs inicial (pendiente cerca de Voc)
    Rs = (voc - vmp) / (imp * 0.1)
    
    # Paso 4: Iterar ajustando Rs para que Pmax_calc = Pmax
    for _ in range(50):
        # Resolver I-V en (vmp, imp) con Rs, Rsh actuales
        Io = isc / (math.exp(voc / (n * Vt)) - 1)
        Iph = isc
        I_calc = _resolver_corriente(vmp, Iph, Io, n, Vt, Rs, Rsh)
        P_calc = vmp * I_calc
        error = (pmax - P_calc) / pmax
        if abs(error) < 1e-6:
            break
        # Ajustar Rs
        Rs += error * 0.01
    
    return {"Rs": round(Rs, 4), "Rsh": round(Rsh, 2), "n": round(n, 3)}

def _resolver_corriente(V, Iph, Io, n, Vt, Rs, Rsh, tol=1e-8, max_iter=100):
    """
    Resuelve I para un V dado usando Newton-Raphson.
    Ecuacion: I = Iph - Io*(exp((V+I*Rs)/(n*Vt))-1) - (V+I*Rs)/Rsh
    """
    I = Iph  # inicial
    for _ in range(max_iter):
        arg = (V + I * Rs) / (n * Vt)
        arg = min(arg, 50)  # proteger overflow
        exp_arg = math.exp(arg)
        f = Iph - Io * (exp_arg - 1) - (V + I * Rs) / Rsh - I
        df = -1 - (Io * Rs / (n * Vt)) * exp_arg - Rs / Rsh
        I_new = I - f / df
        if abs(I_new - I) < tol:
            return I_new
        I = I_new
    return I
```

---

## 3. Flujo de la Simulacion (Actual y Futuro)

### 3.1 Como funciona hoy

```
main():
  1. Crear SistemaSolar()          ← parametros fijos
  2. Bucle de simulacion:
       sistema.step()              ← POA, Tam constantes
  3. Graficar resultados
```

### 3.2 Como debe funcionar (con MQTT y panel seleccionable)

```
prerrequisito: PanelDatabase.cargar("data/paneles/catalogo.json")

main():
  1. cliente_mqtt = ClienteMQTT(broker_host="localhost")
  2. cliente_mqtt.iniciar_carga()
  3. ESPERAR mientras cliente_mqtt._cargando
       (MQTT llena el buffer con datos climaticos)
  4. cliente_mqtt.detener_carga()
  
  5. sistema = SistemaSolar(
         modelo_panel="CS6W-445MS",
         paneles_serie=14,
         cadenas_paralelo=1,
         Vdcref=400,
         clima=cliente_mqtt       ← pasa el cliente, no valores fijos
     )
  
  6. Bucle de simulacion:
       paso = cliente_mqtt.leer_siguiente_paso()
       if paso is None: break
       poa, temp, wind = paso
       sistema.step(poa=poa, Tam=temp)  ← clima variable paso a paso
  
  7. cliente_mqtt.desconectar()
  8. Graficar resultados
```

### 3.3 Interfaz `step()` de SistemaSolar (redisenada)

```python
class SistemaSolar:
    def step(self, poa: float = None, Tam: float = None):
        """
        Avanza un paso de simulacion.
        
        Si poa y Tam no se pasan explicitamente (None),
        se leen del buffer MQTT interno (self._clima).
        """
        if poa is None and self._clima:
            paso = self._clima.leer_siguiente_paso()
            if paso is None:
                return False  # simulación terminada
            poa, Tam, _ = paso
        # ... continuar con el paso normal ...
        return True
```

---

## 4. Formato del Catalogo JSON (Solo Datos Crudos)

```json
{
  "metadata": {
    "version": "2.0",
    "descripcion": "Catalogo de paneles fotovoltaicos - SOLO datos de datasheet",
    "nota": "Rs, Rsh, n se extraen automaticamente. NO se almacenan aqui.",
    "fecha_actualizacion": "2026-07-24"
  },
  "paneles": [
    {
      "fabricante": "Canadian Solar",
      "modelo": "CS6W-445MS",
      "tecnologia": "monocristalino",
      "stc": {
        "pmax": 445,
        "voc": 49.2,
        "isc": 11.45,
        "vmp": 41.2,
        "imp": 10.81
      },
      "coeficientes": {
        "ki": 0.0032,
        "kv": -0.115,
        "noct": 43
      },
      "fisico": {
        "ns": 66,
        "area": 2.08,
        "peso": 23.5
      },
      "extraccion": {
        "metodo": "villalva",
        "n_estimado": null,
        "rs_estimado": null,
        "rsh_estimado": null
      }
    }
  ]
}
```

**Regla**: `extraccion.{n,rs,rsh}_estimado` pueden almacenar el resultado de la ultima extraccion como referencia (cache), pero `extraer_parametros()` es la fuente de verdad y se ejecuta cada vez que se crea un `SolarPanel`.

---

## 5. Resumen de Cambios Respecto al Plan Original

| Aspecto | Plan Original (v1) | Plan Corregido (v2) |
|---------|-------------------|-------------------|
| Rs, Rsh, n en catalogo | Obligatorios | NO se almacenan, se extraen |
| Extraccion de parametros | Opcional, Fase B | Esencial, Fase A |
| Clima | POA, Tam constantes | Via MQTT, buffer circular |
| SistemaSolar.step() | Sin argumentos | step(poa, Tam) opcionales |
| Dependencias nuevas | Ninguna | paho-mqtt |
| Validacion en catalogo | Rs>0, Rsh>>Rs | Solo validar crudos: Voc>Vmp>0, Isc>Imp>0 |

---

## 6. Dependencias Externas (Actualizadas)

- `paho-mqtt`: Cliente MQTT para recibir datos climaticos
- `numpy`, `math`: Calculos del modelo (ya existen)
- El algoritmo de extraccion de parametros es autonomo, no requiere scipy

---

## 7. Plan de Fases (Actualizado)

### Fase 0: Infraestructura MQTT (1 semana)
- [ ] Crear `common/cliente_mqtt.py` con buffer circular
- [ ] Conectar a broker, suscribir topics, recibir datos
- [ ] Prueba: recibir 86400 pasos (1 dia a 1s) sin perdida
- [ ] Integrar en `main.py` actual: cargar clima via MQTT antes de simular

### Fase A: Extraccion de Parametros (1 semana)
- [ ] Implementar `extraer_parametros()` metodo Villalva
- [ ] Implementar `_resolver_corriente()` Newton-Raphson correcto
- [ ] Test: extraer Rs/Rsh/n de KC200GT, comparar con valores conocidos
- [ ] Test: Pmax_calculado = Pmax_datasheet con error < 1%
- [ ] Agregar metodo analitico alternativo

### Fase B: Catalogo de Paneles (1 semana)
- [ ] Crear `Solar/panel_database.py`
- [ ] Formato JSON solo datos crudos (sin Rs, Rsh, n)
- [ ] `agregar_desde_datasheet()` como metodo de clase
- [ ] Poblar con 5-10 paneles comerciales
- [ ] Tests de carga y consistencia

### Fase C: Refactorizar SolarPanel (1 semana)
- [ ] `__init__(params: dict)` en lugar de parametros fijos
- [ ] `SolarPanel.from_database(modelo, **kwargs)` factory method
- [ ] Newton-Raphson corregido en `_resolver_corriente()`
- [ ] `validar_en_stc()` con tolerancia < 2%
- [ ] Agregar `Kv`, `Vmp_ref`, `Imp_ref`, `Pmax_ref`

### Fase D: ArregloFotovoltaico + SistemaSolar (1 semana)
- [ ] Clase `ArregloFotovoltaico` (series/paralelos)
- [ ] SistemaSolar acepta `modelo_panel` + `cliente_mqtt` opcional
- [ ] SistemaSolar.step() lee del buffer MQTT si no se pasan argumentos
- [ ] Tests de integracion con clima simulado via MQTT
