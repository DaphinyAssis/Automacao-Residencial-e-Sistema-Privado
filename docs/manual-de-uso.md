# Manual de Uso — Automação Residencial

## 1. Visão Geral
Este projeto consiste em uma maquete de casa inteligente, utilizando o ESP32 como central de controle para diversos módulos automatizados, todos integrados via MQTT (HiveMQ Cloud) e operáveis pelo app MQTT Dash.

## 2. Ambiente e Ferramentas Necessárias
- **Thonny IDE** (ou similar) para programar e enviar código ao ESP32 via USB
- Conta gratuita no **HiveMQ Cloud** (broker MQTT)
- Celular/tablet com o app **MQTT Dash** instalado
- Componentes eletrônicos conforme cada módulo
- Acesso ao repositório para código, diagramas e documentação complementar

## 3. Estrutura do Repositório
- **/src**: Código-fonte de cada automação
- **/docs**: Fotos, vídeos de funcionamento e esquemas elétricos
- **README.md**: Documentação principal

## 4. Passo a Passo para Instalação e Execução

### a) Preparação Inicial
1. Clone este repositório via `git` no seu PC.
2. Abra os códigos de cada automação na Thonny IDE.
3. Conecte o ESP32 via USB e faça upload do código correspondente.
4. Configure o broker MQTT no código para seu usuário e senha HiveMQ Cloud.

### b) Conexão & Testes
- Assegure que todos os sensores, atuadores (LEDs, motores, servos, chave RFID, etc.) estão conectados conforme esquemas do `/docs`
- No app MQTT Dash, configure os tópicos MQTT para cada módulo, igual aos definidos no código fonte
- Execute testes (via app e sensores) para validar funcionamento

### c) Funcionamento dos Módulos

| Módulo                       | Função                                          | Uso Prático                                                             |
|------------------------------|-------------------------------------------------|-------------------------------------------------------------------------|
| **Iluminação Inteligente**   | Ligar/desligar LEDs via app ou por movimento    | Automático pelo sensor PIR ou manual pelo app                           |
| **Portão Garagem**           | Abrir/fechar portão com servo                   | Botão via app ou remoto por RF                                          |
| **Sensor Estacionamento**    | Indicar proximidade do carro                    | Visualização de LEDs e buzzer conforme distância                        |
| **Monitoramento Banheiro**   | Alertas de umidade/temperatura                  | Acompanha valores pelo app e recebe alertas MQTT                        |
| **Irrigação Automática**     | Aciona LED conforme o comando         | Comando via app                                     |
| **Tranca RFID**              | Desbloqueio por RFID autorizado                 | Aproxima cartão/chaveiro autorizado para abrir                          |
| **Alarme Fumaça/Gás**        | Acionamento por detecção de fumaça/gás          | Visual/Buzzer, alerta diferenciado por tipo                             |
| **Timer Cozinha**            | Temporizador de cozimento no display OLED       | Programa tempo pelo keypad; buzzer ao final                             |
| **Automação Persianas**      | Controle automático/manual das cortinas         | Aciona motor por luminosidade (sensor LDR) ou app                       |
| **Ventilador**               | Liga/desliga por temperatura ou manual          | Sensor DHT22 ativa ventilador automaticamente                           |

## 5. Dicas e Cuidados
- Sempre revise as conexões antes de ligar os circuitos
- Garanta que o broker MQTT esteja ativo durante os testes
- Para cada função, ajuste os limites (ex: temperatura, umidade) diretamente no código se precisar adaptar à sua maquete
- Consulte esquemas e fotos em `/docs` para conferência do hardware

## 6. Expansão e Manutenção
- Novos módulos podem ser implementados no diretório `/src`
- Documente cada modificação para facilitar futuras integrações

## 7. Suporte
Em caso de dúvidas ou problemas, consulte a documentação detalhada no README.md ou abra uma Issue no repositório.
