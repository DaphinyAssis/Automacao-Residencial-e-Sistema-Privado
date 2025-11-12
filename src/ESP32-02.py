import network
import time
from machine import Pin, PWM, time_pulse_us, SPI
import mfrc522
from umqtt.simple import MQTTClient

# --- Buzzer passivo ---
buzzer = PWM(Pin(27))
buzzer.freq(1500)
buzzer.duty_u16(0)

# --- Config Wi-Fi ---
SSID = "xx"
PASSWORD = "xxx"

# --- Config MQTT HiveMQ Cloud ---
MQTT_BROKER = "x.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
CLIENT_ID = "smart_home"
MQTT_USER = "x"
MQTT_PASS = "xxx"

# --- Servo ---
servo = PWM(Pin(4))
servo.freq(50)

# --- RF 433MHZ ---
rf_pin = Pin(15, Pin.IN)

# --- Sensor de estacionamento (HC-SR04) ---
trig = Pin(18, Pin.OUT)
echo = Pin(5, Pin.IN, Pin.PULL_DOWN)

# --- LEDs ---
led_g = Pin(14, Pin.OUT)
led_y = Pin(12, Pin.OUT)
led_r = Pin(13, Pin.OUT)

# --- Variáveis de controle ---
servo_pos = 0              
ultimo_estado = 0         
distancia_anterior = None
ultimo_movimento = time.time()
INACTIVITY_TIMEOUT = 3  
THRESHOLD = 0.5          
sensor_ativo = False

# ----- Pinos RC522 -----
SCK  = 32
MOSI = 33
MISO = 25
RST  = 26
CS   = 21

# ----- Pino do MOSFET / Solenoide -----
SOLENOID_PIN = 19
PULSE_MS = 10000   

# ----- Lista de UIDs permitidos -----
AUTHORIZED = {
    "931EFD2C",
}

# ----- Tópicos MQTT -----
TOPIC_RFID = b"casa/tranca/rfid"
TOPIC_TR_STATUS = b"casa/tranca/status"
TOPIC_TR_EVENTO = b"casa/tranca/evento"
TOPIC_GARAGEM_PORTAO = b"garagem/portao"
TOPIC_GARAGEM_SENSOR = b"garagem/sensor"
TOPIC_TRANCA_CMD = b"casa/tranca"

# Inicializa SPI e RC522
spi = SPI(1, baudrate=1000000, polarity=0, phase=0,
          sck=Pin(SCK), mosi=Pin(MOSI), miso=Pin(MISO))
rdr = mfrc522.MFRC522(spi=spi, gpioRst=Pin(RST), gpioCs=Pin(CS))

# Saída para o MOSFET
solenoid = Pin(SOLENOID_PIN, Pin.OUT, value=0)

print("Aproxime a tag...")
last_uid = None
last_trigger_ms = 0

# --- MQTT globals ---
client = None
last_io = 0  # ticks_ms do último tráfego (publish/ping)

# --- Utilitário: dormir "bombando" MQTT ---
def pump_sleep_ms(ms, step=20):
    t0 = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), t0) < ms:
        try:
            client.check_msg()
        except Exception:
            reconnect_mqtt()
        mqtt_heartbeat()
        time.sleep_ms(step)

# --- Heartbeat / reconexão MQTT ---
def mqtt_heartbeat():
    global last_io, client
    now = time.ticks_ms()
    # envia ping se 30s sem tráfego
    if time.ticks_diff(now, last_io) > 30000:
        try:
            client.ping()
            last_io = now
        except Exception:
            reconnect_mqtt()

def safe_publish(topic, payload, retain=False):
    global last_io
    try:
        if isinstance(payload, str):
            payload = payload.encode()
        client.publish(topic, payload, retain=retain)
        last_io = time.ticks_ms()
    except Exception:
        reconnect_mqtt()
        client.publish(topic, payload, retain=retain)
        last_io = time.ticks_ms()

def reconnect_mqtt():
    global client, last_io
    while True:
        try:
            # tenta reconectar e re-subscrever
            client.connect(False) 
            client.subscribe(TOPIC_GARAGEM_PORTAO)
            client.subscribe(TOPIC_GARAGEM_SENSOR)
            client.subscribe(TOPIC_TRANCA_CMD)
            last_io = time.ticks_ms()
            break
        except Exception:
            time.sleep(2)

def hex_uid(raw):
    return "".join("{:02X}".format(x) for x in raw)

def trigger_solenoid(ms=PULSE_MS):
    solenoid.value(1)
    pump_sleep_ms(ms)
    solenoid.value(0)

# --- Funções do servo ---
def set_servo_angle(angle):
    duty = int((angle / 180.0 * 5000) + 2500)
    servo.duty_u16(duty)

def move_servo_slow(start_angle, end_angle, step=1, delay=20):
    if start_angle < end_angle:
        rng = range(start_angle, end_angle + 1, step)
    else:
        rng = range(start_angle, end_angle - 1, -step)
    for angle in rng:
        set_servo_angle(angle)
        pump_sleep_ms(int(delay))

def controlar_servo_rf():
    global servo_pos, ultimo_estado
    estado = rf_pin.value()
    if estado == 1 and ultimo_estado == 0:
        if servo_pos == 0:
            move_servo_slow(0, 110, step=2, delay=20)
            servo_pos = 110
        else:
            move_servo_slow(110, 0, step=2, delay=20)
            servo_pos = 0
        pump_sleep_ms(300)  # debouncing com loop MQTT
    ultimo_estado = estado

# --- Filtragem e histerese do HC-SR04 ---
MIN_CM = 2
MAX_CM = 400
MIN_US = int(MIN_CM * 58)   
MAX_US = int(MAX_CM * 58)    

T_NEAR = 5
T_FAR  = 12
H      = 1
zona_atual = "FAR" 

def medir_distancia_raw():
    trig.value(0)
    time.sleep_us(2)
    trig.value(1)
    time.sleep_us(10)
    trig.value(0)
    _ = time_pulse_us(echo, 0, 10000)
    dur = time_pulse_us(echo, 1, 30000)
    if dur < MIN_US or dur > MAX_US:
        return None
    return dur / 58.0  # cm

def mediana(vals):
    vals = sorted(vals)
    n = len(vals)
    if n == 0:
        return None
    m = n // 2
    return vals[m] if n % 2 else 0.5 * (vals[m-1] + vals[m])

def medir_distancia_filtrada(n=5, tentativas=8, pausa_ms=20):
    amostras = []
    for _ in range(tentativas):
        d = medir_distancia_raw()
        if d is not None:
            amostras.append(d)
            if len(amostras) >= n:
                break
        pump_sleep_ms(pausa_ms)
    return mediana(amostras)

def medir_distancia():
    return medir_distancia_filtrada()

def atualizar_sensor():
    global distancia_anterior, ultimo_movimento, zona_atual
    if not sensor_ativo:
        return

    d = medir_distancia()
    if d is None:
        d = distancia_anterior if distancia_anterior is not None else 20

    print("Distância (filtrada):", round(d, 2), "cm")

    if distancia_anterior is None or abs(d - distancia_anterior) >= THRESHOLD:
        distancia_anterior = d
        ultimo_movimento = time.time()

    if time.time() - ultimo_movimento > INACTIVITY_TIMEOUT:
        led_g.value(0)
        led_y.value(0)
        led_r.value(0)
        buzzer.duty_u16(0)
        return

    if zona_atual == "NEAR":
        if d >= T_NEAR + H:
            zona_atual = "MID" if d <= T_FAR else "FAR"
    elif zona_atual == "FAR":
        if d <= T_FAR - H:
            zona_atual = "MID" if d > T_NEAR else "NEAR"
    else:  # MID
        if d <= T_NEAR - H:
            zona_atual = "NEAR"
        elif d >= T_FAR + H:
            zona_atual = "FAR"

    led_r.value(1 if zona_atual == "NEAR" else 0)
    led_y.value(1 if zona_atual == "MID" else 0)
    led_g.value(1 if zona_atual == "FAR" else 0)

    # Padrões de beep com MQTT ativo entre pulsos
    def beep(on_ms, off_ms):
        buzzer.duty_u16(30000)
        pump_sleep_ms(on_ms)
        buzzer.duty_u16(0)
        pump_sleep_ms(off_ms)

    if 0 < d <= 5:
        beep(120, 120)
    elif 5 < d <= 10:
        beep(250, 250)
    elif 10 < d <= 15:
        beep(400, 400)
    else:
        buzzer.duty_u16(0)
        pump_sleep_ms(500)

# --- Função MQTT ---
def mqtt_callback(topic, msg):
    global servo_pos, sensor_ativo
    topic = topic.decode()
    msg = msg.decode().upper()

    if topic == "garagem/portao":
        if msg in ["OPEN", "1"]:
            move_servo_slow(servo_pos, 110)
            servo_pos = 110
        elif msg in ["CLOSE", "0"]:
            move_servo_slow(servo_pos, 0)
            servo_pos = 0

    if topic == "garagem/sensor":
        if msg in ["ON", "1"]:
            sensor_ativo = True
        elif msg in ["OFF", "0"]:
            sensor_ativo = False
            led_g.value(0)
            led_y.value(0)
            led_r.value(0)
            buzzer.duty_u16(0)

    if topic == "casa/tranca":
        if msg in ["OPEN", "1"]:
            print("MQTT → abrir tranca")
            trigger_solenoid()
            safe_publish(TOPIC_TR_STATUS, b"OPEN")
        elif msg in ["CLOSE", "0"]:
            print("MQTT → fechar tranca (ignorado, solenoide é pulso)")
            safe_publish(TOPIC_TR_STATUS, b"CLOSED")

# --- Conectar Wi-Fi ---
def conectar_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    # Modo performance (quando suportado) para reduzir latências e perdas
    try:
        wlan.config(pm=network.WLAN.PM_PERFORMANCE)
    except Exception:
        pass
    if not wlan.isconnected():
        wlan.connect(SSID, PASSWORD)
        while not wlan.isconnected():
            time.sleep_ms(100)
    print("Conectado ao Wi-Fi:", wlan.ifconfig())

# --- Main ---
def main():
    global client, last_uid, last_trigger_ms, last_io
    set_servo_angle(servo_pos)
    conectar_wifi()
    client = MQTTClient(
        CLIENT_ID,
        MQTT_BROKER,
        port=MQTT_PORT,
        user=MQTT_USER,
        password=MQTT_PASS,
        keepalive=60, 
        ssl=True,
        ssl_params={"server_hostname": MQTT_BROKER}
    )
    client.set_callback(mqtt_callback)
    client.timeout = 10
    client.connect()
    client.subscribe(TOPIC_GARAGEM_PORTAO)
    client.subscribe(TOPIC_GARAGEM_SENSOR)
    client.subscribe(TOPIC_TRANCA_CMD)
    print("Conectado ao MQTT e inscrito em garagem/portao, garagem/sensor e casa/tranca")
    last_io = time.ticks_ms()

    while True:
        # loop MQTT
        try:
            client.check_msg()
        except Exception:
            reconnect_mqtt()
        mqtt_heartbeat()

        controlar_servo_rf()
        atualizar_sensor()

        # ---- RFID / Solenoide ----
        (stat, _) = rdr.request(rdr.REQIDL)
        if stat == rdr.OK:
            (stat2, raw_uid) = rdr.anticoll()
            if stat2 == rdr.OK and len(raw_uid) >= 4:
                uid = hex_uid(raw_uid[:4])
                now = time.ticks_ms()
                if uid != last_uid or time.ticks_diff(now, last_trigger_ms) > 1500:
                    print("UID detectado:", uid)
                    allowed = (not AUTHORIZED) or (uid in AUTHORIZED)
                    evt = '{{"uid":"{}","allowed":{},"ts":{}}}'.format(
                        uid, str(allowed).lower(), int(time.time())
                    ).encode()
                    safe_publish(TOPIC_RFID, evt)

                    if allowed:
                        print("Acesso permitido → acionando solenoide")
                        trigger_solenoid()
                        safe_publish(TOPIC_TR_EVENTO, ("UID {} permitido".format(uid)).encode())
                        safe_publish(TOPIC_TR_STATUS, b"OPEN")
                    else:
                        print("Acesso negado")
                        safe_publish(TOPIC_TR_EVENTO, ("UID {} negado".format(uid)).encode())
                        safe_publish(TOPIC_TR_STATUS, b"CLOSED")

                    last_uid = uid
                    last_trigger_ms = now
                rdr.halt()

        pump_sleep_ms(100) 

if __name__ == "__main__":
    main()

