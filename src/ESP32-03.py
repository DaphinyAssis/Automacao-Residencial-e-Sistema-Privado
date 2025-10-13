# main.py - Smart Home - controle LEDs, PIR, persiana e irrigação via MQTT
# Baseado no código fornecido pelo usuário. MicroPython (ESP32).

import network
import time
from machine import Pin, PWM, ADC
from umqtt.simple import MQTTClient

# --------------------- CONFIG ---------------------
SSID = "batcaverna"
PASSWORD = "eusouobatman"

MQTT_BROKER = "76a060ba0e5e4996b1e10d38c3bfde9b.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
CLIENT_ID = b"smart_home_esp32"
MQTT_USER = "speedy"
MQTT_PASS = "Master123"

# pinos MOSFET (PWM) -> correspondem aos cômodos abaixo
MOSFET_PINS = {
    "garagem": 15,
    "sala": 13,
    "cozinha": 14,
    "quarto": 27,
    "banheiro": 25,
    "area_externa": 33,
}

ROOMS = list(MOSFET_PINS.keys())

# PIRs (para garagem e area_externa)
PIR_PINS = {
    "garagem": 34,
    "area_externa": 35,
}

PIR_AUTO_DURATION = 3 * 60  # segundos (3 minutos)

# LDR (VP) - ADC pin. VP tipicamente GPIO36; se for outro, ajuste.
LDR_PIN = 36
LDR_THRESHOLD = 2000  # ajustar conforme leitura (0-4095)

# Persiana (ponte H)
BLIND_ENA_PIN = 21  # PWM (velocidade/opcional)
BLIND_IN1_PIN = 22
BLIND_IN2_PIN = 23

# Irrigação
IRRIGATION_PIN = 18  # mosfet para bomba
RESERVOIR_SWITCH_PIN = 5  # float switch (digital input)

# MQTT topics
# - ligar/desligar por cômodo: "home/<room>/set" payload "ON"/"OFF"
# - intensidade por cômodo: "home/<room>/brightness" payload "0"-"100"
# - controlar todas: "home/all/set" e "home/all/brightness"
# - persiana auto: "home/blind/auto" payload "ON"/"OFF"
# - persiana manual: "home/blind/manual" payload "OPEN"/"CLOSE"/"STOP"
# - irrigação: "home/irrigation/set" payload "ON"/"OFF"
# - status: assistant publica em "home/<room>/status", "home/irrigation/status", "home/blind/status"
TOPIC_PREFIX = "home/"

# --------------------------------------------------

# estado interno
wifi_connected = False
client = None

# PWM objects for lights
lights_pwm = {}
lights_state = {}        # {"room": {"on": bool, "brightness": 0-100, "pir_auto_enabled": bool}}
for r in ROOMS:
    lights_state[r] = {"on": False, "brightness": 100, "pir_auto_enabled": (r in PIR_PINS)}

# PIR state: tracks last trigger time
pir_last_trigger = {r: 0 for r in PIR_PINS.keys()}

# PWM frequency for LEDs (ajuste se necessário)
PWM_FREQ = 1000  # Hz

# Inicializa hardware
def hw_init():
    global lights_pwm, adc_ldr, blind_ena_pwm, blind_in1, blind_in2
    # criar PWMs para MOSFETs
    for room, pin_no in MOSFET_PINS.items():
        p = PWM(Pin(pin_no), freq=PWM_FREQ)
        p.duty_u16(0)
        lights_pwm[room] = p

    # PIRs
    for room, pin_no in PIR_PINS.items():
        Pin(pin_no, Pin.IN)

    # ADC LDR
    adc_ldr = ADC(Pin(LDR_PIN))
    adc_ldr.atten(ADC.ATTN_11DB)
    # ADC width default 12 bits (0-4095)

    # Persiana (ponte H)
    blind_ena_pwm = PWM(Pin(BLIND_ENA_PIN), freq=1000)
    blind_ena_pwm.duty_u16(0)
    blind_in1 = Pin(BLIND_IN1_PIN, Pin.OUT)
    blind_in2 = Pin(BLIND_IN2_PIN, Pin.OUT)

    # Irrigação
    Pin(IRRIGATION_PIN, Pin.OUT, value=0)

    # Reservatório
    Pin(RESERVOIR_SWITCH_PIN, Pin.IN)

# ----------------- WiFi e MQTT -----------------
def conectar_wifi():
    global wifi_connected
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(SSID, PASSWORD)
        t0 = time.time()
        while not wlan.isconnected():
            time.sleep(0.5)
            # timeout opcional
            if time.time() - t0 > 15:
                break
    wifi_connected = wlan.isconnected()
    if wifi_connected:
        print("WiFi conectado:", wlan.ifconfig())
    else:
        print("Falha ao conectar WiFi")

def mqtt_connect():
    global client
    client = MQTTClient(
        CLIENT_ID, MQTT_BROKER, port=MQTT_PORT,
        user=MQTT_USER, password=MQTT_PASS,
        ssl=True, ssl_params={"server_hostname": MQTT_BROKER}
    )
    client.set_callback(mqtt_callback)
    client.connect()
    # subscribes
    client.subscribe(b"home/+/set")
    client.subscribe(b"home/+/brightness")
    client.subscribe(b"home/all/set")
    client.subscribe(b"home/all/brightness")
    client.subscribe(b"home/blind/auto")
    client.subscribe(b"home/blind/manual")
    client.subscribe(b"home/irrigation/set")
    print("MQTT conectado e inscrito nos tópicos.")

# ----------------- utilidades luzes -----------------
def brightness_to_duty16(b):
    # b: 0-100 -> duty_u16 0-65535
    if b <= 0:
        return 0
    if b >= 100:
        return 65535
    return int(b * 65535 / 100)

def set_room_brightness(room, brightness):
    brightness = max(0, min(100, int(brightness)))
    lights_state[room]["brightness"] = brightness
    if lights_state[room]["on"]:
        lights_pwm[room].duty_u16(brightness_to_duty16(brightness))
    else:
        lights_pwm[room].duty_u16(0)
    publish_state(room)

def set_room_onoff(room, on):
    lights_state[room]["on"] = bool(on)
    if lights_state[room]["on"]:
        lights_pwm[room].duty_u16(brightness_to_duty16(lights_state[room]["brightness"]))
    else:
        lights_pwm[room].duty_u16(0)
    publish_state(room)

def set_all_brightness(brightness):
    for r in ROOMS:
        set_room_brightness(r, brightness)

def set_all_onoff(on):
    for r in ROOMS:
        set_room_onoff(r, on)

def publish_state(room):
    try:
        topic = (TOPIC_PREFIX + room + "/status").encode()
        payload = ("ON" if lights_state[room]["on"] else "OFF") + ",BRIGHT=" + str(lights_state[room]["brightness"])
        client.publish(topic, payload)
    except Exception as e:
        print("Erro publish_state:", e)

# ----------------- PIR handling -----------------
def handle_pir():
    now = time.time()
    for room, pin_no in PIR_PINS.items():
        pin = Pin(pin_no, Pin.IN)
        if pin.value() == 1:
            # trigger
            pir_last_trigger[room] = now
            # se PIR auto habilitado liga a luz por PIR_AUTO_DURATION
            if lights_state.get(room, {}).get("pir_auto_enabled", False):
                print("PIR detectado em", room)
                # liga na intensidade setada
                set_room_onoff(room, True)
        # se já houve trigger e tempo expirou, desligar se não foi ligado manualmente
        if pir_last_trigger[room] != 0 and (now - pir_last_trigger[room]) > PIR_AUTO_DURATION:
            # somente desliga se estado foi ligado por PIR (não distinguimos origem aqui,
            # então desliga somente se atualmente ON e pir_auto_enabled)
            if lights_state[room]["on"] and lights_state[room]["pir_auto_enabled"]:
                print("PIR auto duration ended -> desligando", room)
                set_room_onoff(room, False)
            pir_last_trigger[room] = 0

# ----------------- LDR + persiana -----------------
blind_auto_enabled = True

def read_ldr():
    try:
        return adc_ldr.read()  # 0-4095
    except:
        return None

def blind_open():
    print("Persiana: ABRIR")
    blind_in1.value(1)
    blind_in2.value(0)
    blind_ena_pwm.duty_u16(40000)  # velocidade - ajuste
    client.publish(b"home/blind/status", b"OPEN")

def blind_close():
    print("Persiana: FECHAR")
    blind_in1.value(0)
    blind_in2.value(1)
    blind_ena_pwm.duty_u16(40000)
    client.publish(b"home/blind/status", b"CLOSED")

def blind_stop():
    print("Persiana: STOP")
    blind_in1.value(0)
    blind_in2.value(0)
    blind_ena_pwm.duty_u16(0)
    client.publish(b"home/blind/status", b"STOPPED")

# Lógica: assumimos que se LDR indicar claro (valor baixo ou alto depende do LDR + pull),
# você pode ajustar LDR_THRESHOLD e a direção abaixo. A maioria dos LDR+divider
# retorna valores maiores com mais luz. Ajuste se necessário.
def handle_ldr_and_blind():
    if not blind_auto_enabled:
        return
    val = read_ldr()
    if val is None:
        return
    # se claro -> abrir persiana; se escuro -> fechar
    if val > LDR_THRESHOLD:
        # muito claro
        blind_open()
    else:
        blind_close()

# ----------------- Irrigação -----------------
def irrigation_set(on):
    Pin(IRRIGATION_PIN, Pin.OUT).value(1 if on else 0)
    client.publish(b"home/irrigation/status", b"ON" if on else b"OFF")

def reservoir_ok():
    # float switch: ajustar lógica (0 ou 1 dependendo do seu sensor)
    s = Pin(RESERVOIR_SWITCH_PIN, Pin.IN).value()
    # assumimos: 1 = água presente; 0 = vazio -> ajuste conforme seu hardware
    return bool(s)

# ----------------- MQTT callback -----------------
def mqtt_callback(topic, msg):
    try:
        topic = topic.decode()
        msg = msg.decode().strip()
        print("MQTT <-", topic, msg)
        # tratar tópicos home/<room>/set e /brightness
        parts = topic.split('/')
        if len(parts) >= 3 and parts[0] == "home":
            if parts[1] == "all":
                # home/all/set ou home/all/brightness
                if parts[2] == "set":
                    if msg.upper() in ("ON", "1"):
                        set_all_onoff(True)
                    elif msg.upper() in ("OFF", "0"):
                        set_all_onoff(False)
                elif parts[2] == "brightness":
                    try:
                        b = int(msg)
                        set_all_brightness(b)
                    except:
                        print("brightness inválido:", msg)
                return
            if parts[1] == "blind":
                if parts[2] == "auto":
                    global blind_auto_enabled
                    blind_auto_enabled = (msg.upper() in ("ON", "1"))
                    client.publish(b"home/blind/status", b"AUTO_ON" if blind_auto_enabled else b"AUTO_OFF")
                    return
                if parts[2] == "manual":
                    cmd = msg.upper()
                    if cmd == "OPEN":
                        blind_open()
                    elif cmd == "CLOSE":
                        blind_close()
                    elif cmd == "STOP":
                        blind_stop()
                    return
            if parts[1] == "irrigation":
                if parts[2] == "set":
                    if msg.upper() in ("ON", "1"):
                        irrigation_set(True)
                    elif msg.upper() in ("OFF", "0"):
                        irrigation_set(False)
                    return
            # caso normal: home/<room>/set ou home/<room>/brightness
            room = parts[1]
            if room in ROOMS:
                if parts[2] == "set":
                    if msg.upper() in ("ON", "1"):
                        set_room_onoff(room, True)
                    elif msg.upper() in ("OFF", "0"):
                        set_room_onoff(room, False)
                elif parts[2] == "brightness":
                    try:
                        b = int(msg)
                        set_room_brightness(room, b)
                    except:
                        print("brightness inválido:", msg)
                return
    except Exception as e:
        print("Erro no mqtt_callback:", e)

# ----------------- Main loop -----------------
def main():
    hw_init()
    conectar_wifi()
    try:
        mqtt_connect()
    except Exception as e:
        print("Erro ao conectar MQTT:", e)
        # tenta conectar sem SSL (fallback) ou reiniciar - não implementado automaticamente aqui

    last_ldr_check = 0
    last_pir_check = 0
    last_reservoir_publish = 0

    while True:
        # checar mensagens MQTT (não bloqueante)
        try:
            client.check_msg()
        except Exception as e:
            # tentar reconectar se der problema
            print("MQTT check_msg erro:", e)
            try:
                mqtt_connect()
            except Exception as e2:
                print("Falha reconectar MQTT:", e2)
            time.sleep(1)

        # PIR: checar frequentemente
        if time.time() - last_pir_check > 0.5:
            handle_pir()
            last_pir_check = time.time()

        # LDR e persiana: checar a cada 2s (ajustável)
        if time.time() - last_ldr_check > 2:
            handle_ldr_and_blind()
            last_ldr_check = time.time()

        # publicar estado do reservatório periodicamente
        if time.time() - last_reservoir_publish > 10:
            ok = reservoir_ok()
            client.publish(b"home/irrigation/reservoir", b"OK" if ok else b"EMPTY")
            last_reservoir_publish = time.time()

        time.sleep(0.1)

if __name__ == "__main__":
    main()
