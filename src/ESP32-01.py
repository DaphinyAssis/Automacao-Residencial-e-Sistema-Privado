import network
import time
from machine import Pin, ADC, PWM, I2C
import ssd1306
from umqtt.simple import MQTTClient
import dht 

# --- Buzzer do timer ---
buzzer_timer = PWM(Pin(15))
buzzer_timer.freq(2000)
buzzer_timer.duty_u16(0)

# --- Buzzer de alarme ---
buzzer = PWM(Pin(27))
buzzer.duty_u16(0)

# --- Config Wi-Fi ---
SSID = "batcaverna"
PASSWORD = "eusouobatman"

# --- Config MQTT HiveMQ Cloud ---
MQTT_BROKER = "numeroaqui.s1.eu.hivemq.cloud" #o endereço do broker está correto no codigo do ESP32, foi retirado do github o endereço real por motivos de segurança
MQTT_PORT = 8883
CLIENT_ID = "smart_home"
MQTT_USER = "speedy"
MQTT_PASS = "teste"

# --- Config do mosfet ---
rele_ventilador = Pin(5, Pin.OUT)
rele_ventilador.value(0)

override_ventilador = None 

# --- LEDs ---
leds = {
    "gas": Pin(25, Pin.OUT),
    "fumaca": Pin(26, Pin.OUT),
}

# --- MQ-2 ---
mq2 = ADC(Pin(34))
mq2.atten(ADC.ATTN_11DB)
limiarGas = 1500
limiarFumaca = 2500

# --- DHT22 ---
dht22 = dht.DHT22(Pin(23))

# --- DHT11 ---
dht11 = dht.DHT11(Pin(13))

# --- Estados ---
estado_leds = {nome: False for nome in leds}
manual_override = {nome: False for nome in leds}
alarme_ativo = None
alarme_start = 0
ALARME_MIN_MS = 3000
client = None

# --- OLED ---
i2c = I2C(0, scl=Pin(21), sda=Pin(22))
oled = ssd1306.SSD1306_I2C(128, 64, i2c)

# --- Keypad ---
ROWS = [Pin(32, Pin.OUT), Pin(33, Pin.OUT), Pin(19, Pin.OUT), Pin(18, Pin.OUT)]
COLS = [Pin(4, Pin.IN, Pin.PULL_DOWN), Pin(14, Pin.IN, Pin.PULL_DOWN), Pin(12, Pin.IN, Pin.PULL_DOWN)]
KEYS = [
    ["1","2","3"],
    ["4","5","6"],
    ["7","8","9"],
    ["*","0","#"]
]

# --- Timer ---
timer_total = 0
timer_restante = 0
modo_timer = "idle"
ultimo_tick = 0

timer_bip_ativo = False
bip_repeticoes = 0
ultimo_pulso = 0
BIP_DURACAO = 700
BIP_INTERVALO = 300
PAUSA_PARES = 1000

# --- Funções Display ---
def center_text(text, y):
    x = (128 - len(text)*8)//2
    oled.text(text, x, y)

def tela_inicial():
    oled.fill(0)
    center_text("TIMER COZINHA", 10)
    center_text("Press *", 35)
    oled.show()

def tela_config(tempo_str="00:00"):
    oled.fill(0)
    center_text("Defina o tempo", 5)
    oled.rect(28, 22, 72, 18, 1)
    center_text(tempo_str, 25)
    oled.text("* apagar", 0, 50)
    oled.text("# ok", 90, 50)
    oled.show()

def tela_timer():
    oled.fill(0)
    center_text("Tempo restante", 5)
    m = timer_restante // 60
    s = timer_restante % 60
    tempo = "{:02d}:{:02d}".format(m, s)
    center_text(tempo, 25)
    progresso = 1 - (timer_restante / timer_total if timer_total > 0 else 0)
    largura = int(120 * progresso)
    oled.rect(4, 50, 120, 10, 1)
    oled.fill_rect(4, 50, largura, 10, 1)
    oled.show()

# --- Leitura Teclado ---
def ler_tecla():
    for i, row in enumerate(ROWS):
        row.value(1)
        for j, col in enumerate(COLS):
            if col.value() == 1:
                row.value(0)
                return KEYS[i][j]
        row.value(0)
    return None

# --- Timer Cozinha ---
def timer_cozinha():
    global timer_total, timer_restante, modo_timer
    tempo_str = ""

    while True:
        digitos = ("0000" + tempo_str)[-4:]
        minutos = int(digitos[:-2])
        segundos = int(digitos[-2:])
        tela_config("{:02d}:{:02d}".format(minutos, segundos))

        tecla = ler_tecla()
        if tecla:
            if tecla == "#":
                break
            elif tecla == "*":
                tempo_str = tempo_str[:-1]
            elif tecla.isdigit() and len(tempo_str) < 4:
                tempo_str += tecla
        time.sleep(0.2)

    digitos = ("0000" + tempo_str)[-4:]
    minutos = int(digitos[:-2])
    segundos = int(digitos[-2:])
    timer_total = minutos * 60 + segundos
    timer_restante = timer_total
    modo_timer = "rodando"

# --- Wi-Fi ---
def conectar_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(SSID, PASSWORD)
    while not wlan.isconnected():
        pass
    print("Wi-Fi conectado:", wlan.ifconfig())

# --- LEDs ---
def acender_led(nome):
    leds[nome].value(1)
    estado_leds[nome] = True
    manual_override[nome] = True
    if client:
        client.publish(f"cozinha/alarme/{nome}/state", "ON")

def apagar_led(nome):
    leds[nome].value(0)
    estado_leds[nome] = False
    manual_override[nome] = False
    if client:
        client.publish(f"cozinha/alarme/{nome}/state", "OFF")

def desligar_tudo():
    global alarme_ativo
    for nome in leds:
        if not manual_override[nome]:
            leds[nome].value(0)
            estado_leds[nome] = False
    buzzer.duty_u16(0)
    alarme_ativo = None

# --- Atualiza alarme ---
def atualizar_alarme():
    global buzzer
    now = time.ticks_ms()
    if alarme_ativo == "gas":
        buzzer.freq(4000)
        buzzer.duty_u16(30000)
    elif alarme_ativo == "fumaca":
        buzzer.freq(4000)
        if (now // 100) % 2 == 0:
            buzzer.duty_u16(30000)
        else:
            buzzer.duty_u16(0)
    else:
        buzzer.duty_u16(0)

# --- Monitorar MQ-2 ---
def monitorar_mq2():
    global alarme_ativo, alarme_start
    leitura = mq2.read()
    now = time.ticks_ms()

    if leitura > limiarFumaca and not manual_override["fumaca"]:
        leds["fumaca"].value(1)
        estado_leds["fumaca"] = True
        leds["gas"].value(0)
        estado_leds["gas"] = False
        if alarme_ativo != "fumaca":
            alarme_ativo = "fumaca"
            alarme_start = now
    elif leitura >= limiarGas and not manual_override["gas"]:
        leds["gas"].value(1)
        estado_leds["gas"] = True
        leds["fumaca"].value(0)
        estado_leds["fumaca"] = False
        if alarme_ativo != "gas":
            alarme_ativo = "gas"
            alarme_start = now
    else:
        if not any(manual_override.values()):
            if alarme_ativo and time.ticks_diff(now, alarme_start) > ALARME_MIN_MS:
                desligar_tudo()

# --- MQTT ---
def mqtt_callback(topic, msg):
    global override_ventilador, alarme_ativo
    topic = topic.decode()
    msg = msg.decode().upper()
    
    # Ventilador Sala de Jogos
    if topic == "jogos/ar":
        if msg in ["ON","0"]:
            rele_ventilador.value(1)
            override_ventilador = True
        elif msg in ["OFF","1"]:
            rele_ventilador.value(0)
            override_ventilador = False
    
    # Alarme Gas / Fumaça
    elif topic == "cozinha/alarme/gas":
        if msg in ["ON","1"]:
            acender_led("gas")
            alarme_ativo = "gas"
        elif msg in ["OFF","0"]:
            apagar_led("gas")
            if alarme_ativo == "gas":
                alarme_ativo = None

    elif topic == "cozinha/alarme/fumaca":
        if msg in ["ON","1"]:
            acender_led("fumaca")
            alarme_ativo = "fumaca"
        elif msg in ["OFF","0"]:
            apagar_led("fumaca")
            if alarme_ativo == "fumaca":
                alarme_ativo = None

# --- Bip do timer ---
def atualizar_buzzer_timer():
    global timer_bip_ativo, bip_repeticoes, ultimo_pulso, modo_timer
    if modo_timer == "fim":
        if not timer_bip_ativo:
            timer_bip_ativo = True
            bip_repeticoes = 0
            ultimo_pulso = time.ticks_ms()
            buzzer_timer.duty_u16(30000)
        else:
            now = time.ticks_ms()
            if bip_repeticoes < 6:
                if (buzzer_timer.duty_u16() > 0 and time.ticks_diff(now, ultimo_pulso) >= BIP_DURACAO) or \
                   (buzzer_timer.duty_u16() == 0 and time.ticks_diff(now, ultimo_pulso) >= BIP_INTERVALO):
                    if buzzer_timer.duty_u16() > 0:
                        buzzer_timer.duty_u16(0)
                    else:
                        if bip_repeticoes % 2 == 0 and bip_repeticoes != 0:
                            time.sleep_ms(PAUSA_PARES)
                        buzzer_timer.duty_u16(30000)
                    bip_repeticoes += 1
                    ultimo_pulso = now
            else:
                buzzer_timer.duty_u16(0)
                timer_bip_ativo = False
                modo_timer = "idle"
    else:
        buzzer_timer.duty_u16(0)
        timer_bip_ativo = False

# --- Main ---
def main():
    global client, timer_restante, modo_timer, ultimo_tick, override_ventilador
    last_dht_read = 0
    last_dht11_read = 0
    last_mq2_read = 0

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
    client.subscribe(b"cozinha/alarme/gas")
    client.subscribe(b"cozinha/alarme/fumaca")
    client.subscribe(b"jogos/ar")
    client.subscribe(b"cozinha/alarme")
    client.subscribe(b"banheiro/temperatura")
    client.subscribe(b"banheiro/umidade")

    while True:
        client.check_msg()
        monitorar_mq2()
        
        if time.time() - last_dht11_read >= 5:
            try:
                dht11.measure()
                temperatura = dht11.temperature()
                client.publish("banheiro/temperatura", str(temperatura))  
                umidade = dht11.humidity()
                client.publish("banheiro/umidade", str(umidade))  
                
            except:
                pass
            last_dht11_read = time.time()

        if time.time() - last_dht_read >= 5:
            try:
                dht22.measure()
                temperatura = dht22.temperature()
                client.publish("jogos/temperatura", str(temperatura)) 


                if override_ventilador is None:
                    if temperatura >= 28:
                        rele_ventilador.value(1)
                    else:
                        rele_ventilador.value(0)
            except:
                pass
            last_dht_read = time.time()

        if modo_timer == "idle":
            tela_inicial()
            tecla = ler_tecla()
            if tecla == "*":
                modo_timer = "config"
        elif modo_timer == "config":
            timer_cozinha()
        elif modo_timer == "rodando":
            if time.time() - ultimo_tick >= 1:
                ultimo_tick = time.time()
                timer_restante -= 1
                if timer_restante <= 0:
                    modo_timer = "fim"
            tela_timer()
        elif modo_timer == "fim":
            tela_timer()
        
        
        if time.time() - last_mq2_read >= 2:
            try:
                valor = mq2.read() 
                client.publish("cozinha/alarme", str(valor))
            except Exception as e:
                print("Erro MQ2:", e)
            last_mq2_read = time.time()
                
        atualizar_alarme()
        atualizar_buzzer_timer()
        
        

if __name__ == "__main__":
    main()

