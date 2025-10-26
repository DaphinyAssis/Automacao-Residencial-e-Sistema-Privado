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
SSID = "batcaverna"
PASSWORD = "eusouobatman"

# --- Config MQTT HiveMQ Cloud ---
MQTT_BROKER = "76a060ba0e5e4996b1e10d38c3bfde9b.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
CLIENT_ID = "smart_home"
MQTT_USER = "speedy"
MQTT_PASS = "Master123"

# --- Servo ---
servo = PWM(Pin(4), freq=50)

# --- RF 433MHZ ---
rf_pin = Pin(15, Pin.IN)

# --- Sensor de estacionamento (HC-SR04) ---
trig = Pin(18, Pin.OUT)
echo = Pin(5, Pin.IN)

# --- LEDs ---
led_g = Pin(14, Pin.OUT)
led_y = Pin(12, Pin.OUT)
led_r = Pin(13, Pin.OUT)

# --- Variáveis de controle ---
servo_pos = 0              # posição inicial
ultimo_estado = 0          # último valor do RF
distancia_anterior = None
ultimo_movimento = time.time()
INACTIVITY_TIMEOUT = 3     # segundos
THRESHOLD = 0.5            # flutuação mínima do sensor
sensor_ativo = False

# ----- Pinos RC522 (corrigido para CS em pino de saída) -----
SCK  = 32
MOSI = 33
MISO = 25
RST  = 26
CS   = 21   # SDA/CS em pino que suporta saída

# ----- Pino do MOSFET / Solenoide -----
SOLENOID_PIN = 19
PULSE_MS = 3000    # tempo energizado

# ----- Lista de UIDs permitidos (hex sem espaços) -----
AUTHORIZED = {
    "931EFD2C",
    # adicione outros UIDs aqui, ex: "DEADBEEF"
}

# Inicializa SPI e RC522
spi = SPI(1, baudrate=1000000, polarity=0, phase=0,
          sck=Pin(SCK), mosi=Pin(MOSI), miso=Pin(MISO))
rdr = mfrc522.MFRC522(spi=spi, gpioRst=Pin(RST), gpioCs=Pin(CS))

# Saída para o MOSFET
solenoid = Pin(SOLENOID_PIN, Pin.OUT, value=0)

print("Aproxime a tag...")
last_uid = None
last_trigger_ms = 0

def hex_uid(raw):
    return "".join("{:02X}".format(x) for x in raw)

def trigger_solenoid(ms=PULSE_MS):
    solenoid.value(1)
    time.sleep_ms(ms)
    solenoid.value(0)

# --- Funções do servo ---
def set_servo_angle(angle):
    duty = int((angle / 180 * 5000) + 2500)
    servo.duty_u16(duty)

def move_servo_slow(start_angle, end_angle, step=1, delay=0.02):
    if start_angle < end_angle:
        for angle in range(start_angle, end_angle + 1, step):
            set_servo_angle(angle)
            time.sleep(delay)
    else:
        for angle in range(start_angle, end_angle - 1, -step):
            set_servo_angle(angle)
            time.sleep(delay)

def controlar_servo_rf():
    global servo_pos, ultimo_estado
    estado = rf_pin.value()
    if estado == 1 and ultimo_estado == 0:
        if servo_pos == 0:
            move_servo_slow(0, 180, step=2, delay=0.02)
            servo_pos = 180
        else:
            move_servo_slow(180, 0, step=2, delay=0.02)
            servo_pos = 0
        time.sleep(0.3)
    ultimo_estado = estado

# --- Função MQTT ---
def mqtt_callback(topic, msg):
    global servo_pos, sensor_ativo
    topic = topic.decode()
    msg = msg.decode().upper()
    # Controle portão
    if topic == "garagem/portao":
        if msg in ["OPEN", "1"]:
            move_servo_slow(servo_pos, 180)
            servo_pos = 180
        elif msg in ["CLOSE", "0"]:
            move_servo_slow(servo_pos, 0)
            servo_pos = 0
    # Controle sensor estacionamento
    if topic == "garagem/sensor":
        if msg in ["ON", "1"]:
            sensor_ativo = True
        elif msg in ["OFF", "0"]:
            sensor_ativo = False
            # desliga LEDs e buzzer imediatamente
            led_g.value(0)
            led_y.value(0)
            led_r.value(0)
            buzzer.duty_u16(0)
     # Controle da tranca via MQTT
    if topic == "casa/tranca":
        if msg in ["OPEN", "1"]:
            print("MQTT → abrir tranca")
            trigger_solenoid()
            client.publish(b"casa/tranca/status", b"OPEN")
        elif msg in ["CLOSE", "0"]:
            print("MQTT → fechar tranca (ignorado, solenoide é pulso)")
            client.publish(b"casa/tranca/status", b"CLOSED")

# --- Sensor de estacionamento simplificado ---
def medir_distancia():
    trig.value(0)
    time.sleep_us(2)
    trig.value(1)
    time.sleep_us(10)
    trig.value(0)
    duracao = time_pulse_us(echo, 1, 30000)
    if duracao <= 0:
        return None  # leitura inválida
    distancia = duracao / 58
    return distancia

def atualizar_sensor():
    global distancia_anterior, ultimo_movimento
    if not sensor_ativo:
        return  # sensor desligado
    d = medir_distancia()
    if d is None:
        d = distancia_anterior if distancia_anterior else 20  # fallback
    # printa no terminal
    print("Distância:", round(d, 2), "cm")
    # detecta movimento
    if distancia_anterior is None or abs(d - distancia_anterior) >= THRESHOLD:
        distancia_anterior = d
        ultimo_movimento = time.time()
    # desliga LEDs e buzzer se parado > INACTIVITY_TIMEOUT
    if time.time() - ultimo_movimento > INACTIVITY_TIMEOUT:
        led_g.value(0)
        led_y.value(0)
        led_r.value(0)
        buzzer.duty_u16(0)
        return
    # LEDs
    led_g.value(d > 12)
    led_y.value(5 < d <= 12)
    led_r.value(d <= 5)
    if 0 < d <= 5:
        buzzer.duty_u16(30000)
        time.sleep(0.12)
        buzzer.duty_u16(0)
        time.sleep(0.12)
    elif 5 < d <= 10:
        buzzer.duty_u16(30000)
        time.sleep(0.25)
        buzzer.duty_u16(0)
        time.sleep(0.25)
    elif 10 < d <= 15:
        buzzer.duty_u16(30000)
        time.sleep(0.4)
        buzzer.duty_u16(0)
        time.sleep(0.4)
    else:  # >15 cm
        buzzer.duty_u16(0)
        time.sleep(0.5)

# --- Conectar Wi-Fi ---
def conectar_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(SSID, PASSWORD)
        while not wlan.isconnected():
            time.sleep(0.5)
    print("Conectado ao Wi-Fi:", wlan.ifconfig())

# --- Main ---
def main():
    global client
    set_servo_angle(servo_pos)
    conectar_wifi()
    client = MQTTClient(
        CLIENT_ID,
        MQTT_BROKER,
        port=MQTT_PORT,
        user=MQTT_USER,
        password=MQTT_PASS,
        ssl=True,
        ssl_params={"server_hostname": MQTT_BROKER}
    )
    client.set_callback(mqtt_callback)
    client.connect()
    client.subscribe(b"garagem/portao")
    client.subscribe(b"garagem/sensor")
    client.subscribe(b"casa/tranca")
    print("Conectado ao MQTT e inscrito em garagem/portao, garagem/sensor e casa/tranca")

    while True:
        controlar_servo_rf()         # checa RF
        client.check_msg()           # checa MQTT
        atualizar_sensor()           # checa sensor de estacionamento
        
        # ---- Código do RFID / Solenoide (adicionado ao loop principal) ----
        global last_uid, last_trigger_ms
        (stat, _) = rdr.request(rdr.REQIDL)
        if stat == rdr.OK:
            (stat2, raw_uid) = rdr.anticoll()
            if stat2 == rdr.OK and len(raw_uid) >= 4:
                uid = hex_uid(raw_uid[:4])
                now = time.ticks_ms()
                if uid != last_uid or time.ticks_diff(now, last_trigger_ms) > 1500:
                    print("UID detectado:", uid)
                    if (not AUTHORIZED) or (uid in AUTHORIZED):
                        print("Acesso permitido → acionando solenoide")
                        trigger_solenoid()
                        client.publish(b"casa/tranca/evento", "UID {} permitido".format(uid))
                        client.publish(b"casa/tranca/status", b"OPEN")
                    else:
                        print("Acesso negado")
                        client.publish(b"casa/tranca/evento", "UID {} negado".format(uid))
                        client.publish(b"casa/tranca/status", b"CLOSED")
                    last_uid = uid
                    last_trigger_ms = now
                rdr.halt()
        time.sleep_ms(100)

if __name__ == "__main__":
    main()

