import network
import time
from machine import Pin, PWM, ADC
from umqtt.simple import MQTTClient

# --------------------- CONFIG ---------------------
SSID = "x"
SENHA = "xx"

MQTT_SERVIDOR = "x.s1.eu.hivemq.cloud"
MQTT_PORTA = 8883
MQTT_CLIENTE_ID = b"casa_inteligente_esp32"
MQTT_USUARIO = "x"
MQTT_SENHA = "xxx"

# Cômodos e pinos dos MOSFETs
MOSFET_PINOS = {
    "jardim": 13,
    "sala": 12,
    "garagem": 14,
    "cozinha": 27,
    "varanda": 26,
    "quarto": 25,
    "banheiro": 15,
}
COMODOS = list(MOSFET_PINOS.keys())

# Sensores de presença (PIR)
PIR_PINOS = {
    "garagem": 34,
}
TEMPO_AUTO_PIR = 1 * 60 

# Sensor de luminosidade (LDR)
LDR_PINO = 35
LIMIAR_LDR = 50 

# Irrigação via LED azul (simulação)
PINO_LED_IRRIGACAO = 21

TOPICO_PREFIXO = "casa/"

# --------------------- ESTADOS ---------------------
wifi_conectado = False
cliente = None

luzes_pwm = {}
estado_luzes = {}
for c in COMODOS:
    estado_luzes[c] = {"ligado": True, "brilho": 100, "pir_auto": (c in PIR_PINOS)}

ultimo_pir = {c: 0 for c in PIR_PINOS.keys()}
PWM_FREQUENCIA = 1000

# Variáveis LDR
ultimo_status_ldr = None
INTERVALO_LDR = 5
ultimo_debug_ldr = 0

# Objetos de hardware globais
led_irrigacao = None
adc_ldr = None

# --------------------- INICIALIZAÇÃO ---------------------
def iniciar_hardware():
    global luzes_pwm, adc_ldr, led_irrigacao

    print("Iniciando hardware...")

    # LEDs (MOSFETs)
    for comodo, pino in MOSFET_PINOS.items():
        pwm = PWM(Pin(pino), freq=PWM_FREQUENCIA)
        pwm.duty_u16(65535)
        luzes_pwm[comodo] = pwm
        print(f"LED {comodo}: GPIO {pino}")

    # PIRs
    for comodo, pino in PIR_PINOS.items():
        Pin(pino, Pin.IN)
        print(f"PIR {comodo}: GPIO {pino}")

    # LDR
    adc_ldr = ADC(Pin(LDR_PINO))
    adc_ldr.atten(ADC.ATTN_11DB)
    adc_ldr.width(ADC.WIDTH_12BIT)
    print(f"LDR: GPIO {LDR_PINO}")

    # Irrigação via LED
    led_irrigacao = Pin(PINO_LED_IRRIGACAO, Pin.OUT)
    led_irrigacao.value(0)
    print(f"Irrigação (LED azul): GPIO {PINO_LED_IRRIGACAO}")

    print("Hardware inicializado!")

# --------------------- LDR ---------------------
def ler_ldr():
    try:
        valor = adc_ldr.read()
        return valor
    except Exception as e:
        print("Erro lendo LDR:", e)
        return None

def classificar_ldr(valor):
    if valor is None:
        return "ERRO"
    if valor < LIMIAR_LDR:
        return "NOITE"
    else:
        return "DIA"

def publicar_status_ldr():
    global ultimo_status_ldr, ultimo_debug_ldr
    valor = ler_ldr()
    if valor is None:
        return

    status_atual = classificar_ldr(valor)

    agora = time.time()
    if agora - ultimo_debug_ldr > 10:
        print(f"LDR Debug: valor={valor}, status={status_atual}, limite={LIMIAR_LDR}")
        ultimo_debug_ldr = agora

    if status_atual != ultimo_status_ldr and status_atual != "ERRO":
        try:
            cliente.publish(b"casa/ldr/status", status_atual.encode())
            print(f"LDR: {valor} -> {status_atual} (Publicado)")
            ultimo_status_ldr = status_atual
        except Exception as e:
            print("Erro publicando LDR:", e)

# Controle automático do jardim baseado no LDR
def tratar_ldr_jardim():
    valor = ler_ldr()
    if valor is None:
        return
    status = classificar_ldr(valor)
    if status == "NOITE" and not estado_luzes["jardim"]["ligado"]:
        print(f"LDR: {valor} -> NOITE -> Ligando luz do jardim")
        ligar_comodo("jardim", True)
    elif status == "DIA" and estado_luzes["jardim"]["ligado"]:
        print(f"LDR: {valor} -> DIA -> Desligando luz do jardim")
        ligar_comodo("jardim", False)

# --------------------- WIFI E MQTT ---------------------
def conectar_wifi():
    global wifi_conectado
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Conectando WiFi...")
        wlan.connect(SSID, SENHA)
        t0 = time.time()
        while not wlan.isconnected():
            time.sleep(0.5)
            if time.time() - t0 > 15:
                break
    wifi_conectado = wlan.isconnected()
    print("Wi-Fi conectado:", wlan.ifconfig() if wifi_conectado else "Falha na conexão")

def conectar_mqtt():
    global cliente
    cliente = MQTTClient(
        MQTT_CLIENTE_ID,
        MQTT_SERVIDOR,
        port=MQTT_PORTA,
        user=MQTT_USUARIO,
        password=MQTT_SENHA,
        ssl=True,
        ssl_params={"server_hostname": MQTT_SERVIDOR}
    )
    cliente.set_callback(receber_mqtt)
    cliente.connect()

    # Inscrever nos tópicos
    cliente.subscribe(b"casa/+/ligar")
    cliente.subscribe(b"casa/+/brilho")
    cliente.subscribe(b"casa/todos/ligar")
    cliente.subscribe(b"casa/todos/brilho")
    cliente.subscribe(b"casa/irrigacao/ligar")
    print("MQTT conectado e inscrito.")

# --------------------- FUNÇÕES DAS LUZES ---------------------
def brilho_para_duty(b):
    b = max(0, min(100, int(b)))
    return int(b * 65535 / 100)

def definir_brilho(comodo, brilho):
    estado_luzes[comodo]["brilho"] = brilho
    if estado_luzes[comodo]["ligado"]:
        luzes_pwm[comodo].duty_u16(brilho_para_duty(brilho))
    else:
        luzes_pwm[comodo].duty_u16(0)
    publicar_estado(comodo)

def ligar_comodo(comodo, ligado):
    estado_luzes[comodo]["ligado"] = bool(ligado)
    if ligado:
        luzes_pwm[comodo].duty_u16(brilho_para_duty(estado_luzes[comodo]["brilho"]))
    else:
        luzes_pwm[comodo].duty_u16(0)
    publicar_estado(comodo)

def definir_brilho_todos(brilho):
    for c in COMODOS:
        definir_brilho(c, brilho)

def ligar_todos(ligado):
    for c in COMODOS:
        ligar_comodo(c, ligado)

def publicar_estado(comodo):
    try:
        topico = (TOPICO_PREFIXO + comodo + "/status").encode()
        payload = ("ON" if estado_luzes[comodo]["ligado"] else "OFF") + ",BRILHO=" + str(estado_luzes[comodo]["brilho"])
        cliente.publish(topico, payload)
    except Exception as e:
        print("Erro publicando estado:", e)

# --------------------- PIR ---------------------
def tratar_pir():
    agora = time.time()
    for comodo, pino in PIR_PINOS.items():
        sensor = Pin(pino, Pin.IN)
        if sensor.value() == 1:
            ultimo_pir[comodo] = agora
            if estado_luzes[comodo]["pir_auto"]:
                ligar_comodo(comodo, True)
        if ultimo_pir[comodo] != 0 and (agora - ultimo_pir[comodo]) > TEMPO_AUTO_PIR:
            if estado_luzes[comodo]["ligado"] and estado_luzes[comodo]["pir_auto"]:
                ligar_comodo(comodo, False)
            ultimo_pir[comodo] = 0

# --------------------- IRRIGAÇÃO (LED) ---------------------
def definir_irrigacao(ligado):
    led_irrigacao.value(1 if ligado else 0)
    cliente.publish(b"casa/irrigacao/status", b"ON" if ligado else b"OFF")

# --------------------- CALLBACK MQTT ---------------------
def receber_mqtt(topico, msg):
    try:
        topico = topico.decode()
        msg = msg.decode().strip()
        print("MQTT <-", topico, msg)
        partes = topico.split('/')
        if len(partes) < 3:
            return

        if partes[1] == "todos":
            if partes[2] == "ligar":
                ligar_todos(msg.upper() in ("ON", "1"))
            elif partes[2] == "brilho":
                try:
                    definir_brilho_todos(int(msg))
                except:
                    pass
            return

        if partes[1] == "irrigacao":
            if partes[2] == "ligar":
                definir_irrigacao(msg.upper() in ("ON", "1"))
                return

        comodo = partes[1]
        if comodo in COMODOS:
            if partes[2] == "ligar":
                ligar_comodo(comodo, msg.upper() in ("ON", "1"))
            elif partes[2] == "brilho":
                try:
                    definir_brilho(comodo, int(msg))
                except:
                    pass

    except Exception as e:
        print("Erro callback MQTT:", e)

# --------------------- LOOP PRINCIPAL ---------------------
def main():
    iniciar_hardware()
    conectar_wifi()
    try:
        conectar_mqtt()
    except Exception as e:
        print("Erro MQTT:", e)

    ultimo_pir_check = 0
    ultimo_ldr_check = 0
    ultimo_ldr_publicacao = 0

    print("Sistema iniciado! Monitorando LDR...")

    while True:
        try:
            cliente.check_msg()
        except Exception as e:
            print("Erro MQTT:", e)
            try:
                conectar_mqtt()
            except:
                pass
            time.sleep(1)

        agora = time.time()

        if agora - ultimo_pir_check > 0.5:
            tratar_pir()
            ultimo_pir_check = agora

        if agora - ultimo_ldr_check > 5:
            tratar_ldr_jardim()
            ultimo_ldr_check = agora

        if agora - ultimo_ldr_publicacao > INTERVALO_LDR:
            publicar_status_ldr()
            ultimo_ldr_publicacao = agora

        time.sleep(0.1)

if __name__ == "__main__":
    main()

