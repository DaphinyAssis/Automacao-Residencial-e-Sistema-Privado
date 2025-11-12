# mfrc522.py - Driver RC522 para MicroPython (ESP32/ESP8266)
# Adaptado de micropython-mfrc522

from machine import Pin
from os import uname
import time

class MFRC522:
    OK = 0
    NOTAGERR = 1
    ERR = 2

    REQIDL = 0x26
    REQALL = 0x52
    AUTHENT1A = 0x60
    AUTHENT1B = 0x61

    def __init__(self, spi, gpioRst, gpioCs):
        self.spi = spi
        self.rst = gpioRst
        self.cs = gpioCs

        self.rst.init(Pin.OUT, value=1)
        self.cs.init(Pin.OUT, value=1)

        self._init()

    def _init(self):
        self.reset()
        self.write_reg(0x2A, 0x8D)
        self.write_reg(0x2B, 0x3E)
        self.write_reg(0x2D, 30)
        self.write_reg(0x2C, 0)
        self.write_reg(0x15, 0x40)
        self.write_reg(0x11, 0x3D)
        self.antenna_on()

    def reset(self):
        self.write_reg(0x01, 0x0F)

    def write_reg(self, reg, val):
        self.cs.value(0)
        self.spi.write(bytearray([(reg << 1) & 0x7E, val]))
        self.cs.value(1)

    def read_reg(self, reg):
        self.cs.value(0)
        self.spi.write(bytearray([((reg << 1) & 0x7E) | 0x80]))
        val = self.spi.read(1)
        self.cs.value(1)
        return val[0]

    def set_bitmask(self, reg, mask):
        tmp = self.read_reg(reg)
        self.write_reg(reg, tmp | mask)

    def clear_bitmask(self, reg, mask):
        tmp = self.read_reg(reg)
        self.write_reg(reg, tmp & (~mask))

    def antenna_on(self):
        if ~(self.read_reg(0x14) & 0x03):
            self.set_bitmask(0x14, 0x03)

    def to_card(self, command, send):
        back_data = []
        back_len = 0
        status = self.ERR
        irq_en = 0x00
        wait_irq = 0x00

        if command == 0x0E:  # MFAuthent
            irq_en = 0x12
            wait_irq = 0x10
        if command == 0x0C:  # Transceive
            irq_en = 0x77
            wait_irq = 0x30

        self.write_reg(0x02, irq_en | 0x80)
        self.clear_bitmask(0x04, 0x80)
        self.set_bitmask(0x0A, 0x80)
        self.write_reg(0x01, 0x00)

        for c in send:
            self.write_reg(0x09, c)

        self.write_reg(0x01, command)

        if command == 0x0C:
            self.set_bitmask(0x0D, 0x80)

        i = 2000
        while True:
            n = self.read_reg(0x04)
            i -= 1
            if ~((i != 0) and not (n & 0x01) and not (n & wait_irq)):
                break

        self.clear_bitmask(0x0D, 0x80)

        if i:
            if (self.read_reg(0x06) & 0x1B) == 0x00:
                status = self.OK

                if n & irq_en & 0x01:
                    status = self.NOTAGERR
                if command == 0x0C:
                    n = self.read_reg(0x0A)
                    last_bits = self.read_reg(0x0C) & 0x07
                    if last_bits:
                        back_len = (n - 1) * 8 + last_bits
                    else:
                        back_len = n * 8
                    if n == 0:
                        n = 1
                    if n > 16:
                        n = 16
                    for _ in range(n):
                        back_data.append(self.read_reg(0x09))
            else:
                status = self.ERR
        return status, back_data, back_len

    def request(self, req_mode):
        self.write_reg(0x0D, 0x07)
        status, back_data, back_bits = self.to_card(0x0C, [req_mode])
        if (status != self.OK) | (back_bits != 0x10):
            status = self.ERR
        return status, back_bits

    def anticoll(self):
        ser_chk = 0
        ser = [0x93, 0x20]
        self.write_reg(0x0D, 0x00)
        status, back_data, back_bits = self.to_card(0x0C, ser)
        if status == self.OK:
            if len(back_data) == 5:
                for i in range(4):
                    ser_chk ^= back_data[i]
                if ser_chk != back_data[4]:
                    status = self.ERR
            else:
                status = self.ERR
        return status, back_data

    def select_tag(self, ser):
        buf = [0x93, 0x70] + ser[:5]
        p_out = self.calulate_crc(buf)
        buf += p_out
        status, back_data, back_len = self.to_card(0x0C, buf)
        if (status == self.OK) and (back_len == 0x18):
            return 1
        return 0

    def calulate_crc(self, data):
        self.clear_bitmask(0x05, 0x04)
        self.set_bitmask(0x0A, 0x80)
        for c in data:
            self.write_reg(0x09, c)
        self.write_reg(0x01, 0x03)
        i = 0xFF
        while True:
            n = self.read_reg(0x05)
            i -= 1
            if not ((i != 0) and not (n & 0x04)):
                break
        return [self.read_reg(0x22), self.read_reg(0x21)]
    
    def halt(self):
        buf = [0x50, 0x00]
        crc = self.calulate_crc(buf)
        buf += crc
        self.to_card(0x0C, buf)


