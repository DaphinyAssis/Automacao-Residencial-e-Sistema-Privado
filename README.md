# Smart Home

Este projeto tem como objetivo a construção de uma maquete de casa inteligente (Smart Home) com diferentes funcionalidades automatizadas, utilizando o ESP32 como central de controle e comunicação via MQTT.

Este documento especifica todas as automações implementadas, detalhando os módulos, os componentes eletrônicos utilizados, a lógica de funcionamento e a integração com o aplicativo MQTT Dash. Serve como guia técnico e documentação de referência para reproduzir e entender o funcionamento de cada automação.

## Objetivos do Projeto
- Implementar funcionalidades de automação residencial de forma prática e didática.
- Documentar cada módulo com componentes, código-fonte e fluxo de operação.
- Demonstrar integração dos módulos via HiveMQ Cloud e controle pelo MQTT Dash.
- Fornecer evidências de funcionamento para validação e testes.
- Estruturar o projeto para desenvolvimento contínuo e entregas controladas via GitHub.

## Ferramentas e Ambiente de Desenvolvimento
- **Thonny IDE**: utilizada para programar o ESP32 com MicroPython.
  - Permite escrever, testar e enviar código diretamente ao ESP32 via USB.
  - Monitoramento serial e depuração integrada.
- **HiveMQ Cloud**: broker MQTT na nuvem, gerenciando tópicos e mensagens entre dispositivos.
- **MQTT Dash**: aplicativo móvel para enviar comandos e visualizar dados das automações em tempo real.

## Estrutura do Repositório
- **/src** → Código-fonte para cada automação.
- **/docs** → Fotos, vídeos e esquemas dos circuitos.
- **README.md** → Documentação geral do projeto.

## Módulos e Funcionalidades

### Iluminação Inteligente (MQTT, App e Movimento)
O ESP32 controla fitas de LED 12V via MOSFET IRLZ44N, permitindo ligar, desligar e ajustar brilho. Sensores PIR ativam a iluminação automaticamente ao detectar movimento.

**Componentes:**
- 1x Fonte 12V  
- 1x Fonte 5V  
- 9x LED Strip Light 12V  
- 9x MOSFET IRLZ44N  
- 9x Resistores 220Ω  
- 4x Sensores PIR HC-SR501  

---

### Controle do Portão da Garagem
O portão é automatizado com servo motor SG90, controlado pelo ESP32 via módulo RF 433MHz ou app MQTT, permitindo abertura e fechamento remoto ou manual.

**Componentes:**
- 1x Servo motor SG90  
- 1x Kit módulo receptor RF 433MHz  
- 1x Fonte 5V  

---

### Sensor de Estacionamento
Sensor ultrassônico HC-SR04 mede a distância do carro até a parede. O ESP32 aciona buzzer e LEDs (verde, amarelo, vermelho) conforme a proximidade.

**Componentes:**
- 1x Sensor ultrassônico HC-SR04  
- 1x Buzzer passivo  
- 3x LEDs (verde, amarelo, vermelho)  
- 3x Resistores 220Ω  
- 1x Resistor 10kΩ  
- 1x Resistor 20kΩ  
- 1x Fonte 5V  

---

### Monitoramento de Umidade e Temperatura (Banheiro)
O sensor DHT11 monitora temperatura e umidade, enviando alertas via MQTT caso ultrapasse limites definidos.

**Componentes:**
- 1x Fonte 5V  
- 1x Sensor DHT11  
- 1x Resistor 10kΩ (pull-up)  

---

### Irrigação Automática (Reed Switch e Mini Bomba)
Sistema simulado com LEDs azuis e mini bomba 3V, acionados via MQTT. O reed switch monitora o nível do reservatório.

**Componentes:**
- 2x LEDs azuis  
- 1x MOSFET IRLZ44N  
- 1x Mini bomba de água  
- 1x Fonte 5V  
- 1x Reed switch  
- 1x Resistor 10kΩ  
- 3x Resistores 220Ω  
- 1x Diodo 1N4148  

---

### Tranca Eletrônica com RFID
Leitor RFID RC522 libera a trava elétrica 12V apenas para cartões autorizados.

**Componentes:**
- 1x Fonte 12V  
- 1x Fonte 5V  
- 1x Módulo leitor RFID RC522  
- 1x Trava elétrica 12V (solenoide)  
- 1x MOSFET IRLZ44N  
- 1x Cartão/chaveiro RFID  
- 1x Resistor 10kΩ  
- 1x Diodo 1N5408  

---

### Alarme de Fumaça e Gás
O sensor MQ-2 detecta fumaça e gases, acionando LEDs e buzzer. O ESP32 diferencia os alertas conforme o perigo.

**Componentes:**
- 1x Sensor MQ-2  
- 1x LED vermelho  
- 1x LED amarelo  
- 2x Resistores 220Ω  
- 1x Buzzer passivo 5V  
- 1x Fonte 5V  

---

### Timer de Cozinha (Keypad + Display OLED)
Permite programar tempos de cozimento via keypad 4x3 e display OLED. O ESP32 gerencia contagem regressiva e aciona buzzer ao término.

**Componentes:**
- 1x Keypad matricial 4x3  
- 1x Display OLED 0.96" I2C (128x64)  
- 1x Buzzer passivo  

---

### Automação de Persianas
Motor DC controlado por driver L298N enrola/desenrola persianas automaticamente conforme luminosidade detectada pelo sensor LDR ou comandos via MQTT.

**Componentes:**
- 1x Motor DC 3–6V  
- 1x Driver ponte H L298N  
- 1x Sensor LDR  
- 1x Resistor 10kΩ  

---

### Acionamento de Ventilador
Ventilador 5V acionado automaticamente quando temperatura (DHT22) ultrapassa limite definido, ou manualmente via MQTT.

**Componentes:**
- 1x Fonte 5V  
- 1x Ventilador 5V  
- 1x MOSFET IRLZ44N  
- 1x Sensor DHT22  
- 1x Resistor 10kΩ (pull-up)  
