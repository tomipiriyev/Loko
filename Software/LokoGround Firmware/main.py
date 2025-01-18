import machine
from machine import ADC
from machine import Pin, UART, Timer
from time import sleep_ms
from ucryptolib import aes
import ustruct as struct
import ubinascii
import ubluetooth
import json
import _thread
import sys

if 1:  # Must be 1 for real hardware
    VBAT_IN = ADC(Pin(39))
    BUTTON = Pin(35, Pin.IN)
    POWER_CTRL = Pin(12, Pin.OUT)
    LED_BLUE = Pin(21, Pin.OUT)
    LED_RED = Pin(18, Pin.OUT)
    LED_GREEN = Pin(19, Pin.OUT)
    LORA_UART = UART(2, 9600, timeout=100, txbuf=1024, rxbuf=1024)
else:
    # Loko debug board pinout
    VBAT_IN = ADC(Pin(1))
    BUTTON = Pin(0, Pin.IN)
    POWER_CTRL = Pin(12, Pin.OUT)
    LED_BLUE = Pin(47, Pin.OUT)
    LED_RED = Pin(36, Pin.OUT)
    LED_GREEN = Pin(37, Pin.OUT)
    LORA_UART = UART(2, 9600)

use_coommand_line_parser = False

class SETTINGS():

    data = {
        'id2': 0,
        'freq': 868,
        'p2p_key': "00" * 32,
    }

    def __init__(self, file_name='settings.json'):
        self.file_name = file_name
        self.load()

    def save(self):
        print('Save settings to {}:{}'.format(self.file_name, self.data))
        with open(self.file_name, "w") as fp:
            json.dump(self.data, fp)

    def load(self):
        try:
            with open(self.file_name, "r") as fp:
                self.data = json.load(fp)
        except Exception as inst:
            print(inst)
            print("Settings file not found create new and use default settings")
            self.save()
        print('Load settings from {}:{}'.format(self.file_name, self.data))


class COMMAND_RECEIVER():

    def __init__(self, settings_obj):
        self.exit_request = False
        self.settings = settings_obj
        _thread.start_new_thread(self.receiver_thread, ())

    def set_handler(self, tag, number):
        if tag != 'id2' and tag != 'freq':
            print('Wrong set argument')
            return

        try:
            param = int(number)
        except (ValueError, TypeError):
            print("Expected numeric argument")
        else:
            if tag == 'freq' and param > 1000:
                print('Too big frequency argument, expected value in MHZ < 1000')
                return

            self.settings.data[tag] = param
            self.settings.save()

    def get_info(self, *args):
        print('Settings: ', self.settings.data)

    def print_help(self, *args):
        for cmd in self.commands:
            print('{} - {}'.format(cmd, self.commands[cmd]['info']))

    def exit_app(self, *args):
        self.exit_request = True
        sys.exit(1)

    commands = {
        'set': {'handler': set_handler, 'info': '\'set id2 VALUE\' or \'set freq VALUE\''},
        'info': {'handler': get_info, 'info': 'print current settings'},
        'help': {'handler': print_help, 'info': 'show this text'},
        'exit': {'handler': exit_app, 'info': 'test_command'},
    }

    def receiver_thread(self):
        while True:
            try:
                rx_line = input("> ")
            except KeyboardInterrupt:
                print('Ctrl+C pressed')
                exit_app()
            print('!!!' + rx_line)

            if not rx_line:
                continue

            cmd, *params = rx_line.split()
            try:
                handler = self.commands[cmd]['handler']
            except KeyError:
                print('Unknown command')
            else:
                handler(self, *params)


class LOKO_BLE():
    def __init__(self, name):
        # Create internal objects for the onboard LED_BLUE
        # blinking when no BLE device is connected
        # stable ON when connected
        self.led = LED_BLUE
        self.timer1 = Timer(0)
        self.name = name
        self.ble = ubluetooth.BLE()
        self.ble.active(True)
        self.disconnected()
        self.ble.irq(self.ble_irq)
        self.register()
        self.advertiser()
        self.ble.config(gap_name="Loko")
        self.is_connected = False

    def connected(self):
        self.is_connected = True
        self.led.value(0)
        self.timer1.deinit()
        print('Connected')

    def disconnected(self):
        self.is_connected = False
        self.timer1.init(period=300, mode=Timer.PERIODIC,
                         callback=lambda t: self.led.value(not self.led.value()))
        print('Disconnected')

    def ble_irq(self, event, data):
        if event == 1:  # _IRQ_CENTRAL_CONNECT:
            # A central has connected to this peripheral
            self.connected()
        elif event == 2:  # _IRQ_CENTRAL_DISCONNECT:
            # A central has disconnected from this peripheral.
            self.advertiser()
            self.disconnected()
        elif event == 3:  # _IRQ_GATTS_WRITE:
            # A client has written to this characteristic or descriptor.
            ble_msg = self.ble.gatts_read(self.rx).decode('UTF-8').strip()
            print('BLE Rx:', ble_msg)  # TODO: This message do not used

    def register(self):
        # Nordic UART Service (NUS)
        NUS_UUID = '6E400001-B5A3-F393-E0A9-E50E24DCCA9E'
        RX_UUID = '6E400002-B5A3-F393-E0A9-E50E24DCCA9E'
        TX_UUID = '6E400003-B5A3-F393-E0A9-E50E24DCCA9E'
        BLE_NUS = ubluetooth.UUID(NUS_UUID)
        BLE_RX = (ubluetooth.UUID(RX_UUID), ubluetooth.FLAG_WRITE)
        BLE_TX = (ubluetooth.UUID(TX_UUID), ubluetooth.FLAG_NOTIFY)
        BLE_UART = (BLE_NUS, (BLE_TX, BLE_RX,))
        SERVICES = (BLE_UART, )
        ((self.tx, self.rx,), ) = self.ble.gatts_register_services(SERVICES)

    def send(self, data):
        try:
            #self.ble.gatts_write(self.tx, data + '\n', True)
            self.ble.gatts_notify(0,self.tx, data + '\n')
            # self.ble.gatts_notify(0, self.tx, data + '\n') #doesn't work on ESP32S3, got OSError: -128, Remove it after tests on real hardware
        except Exception as inst:
            print('BLE Send error:', inst)

    def advertiser(self):
        name = bytes(self.name, 'UTF-8')
        adv_data = bytearray(b'\x02\x01\x02') + \
            bytearray((len(name) + 1, 0x09)) + name
        self.ble.gap_advertise(100, adv_data)
        print('ADV:', adv_data)


def battery_level():
    VBAT_IN.atten(ADC.ATTN_11DB)  # Adjust this based on your actual setup
    VBAT_IN.width(ADC.WIDTH_12BIT)  # Ensure this matches your earlier setting
    adc_reading = VBAT_IN.read()  # Get the ADC value
   # print(adc_reading)
    max_adc_value = 2455  # Max value for a 12-bit ADC
    max_battery_voltage = 2.1  # Adjust based on your battery's characteristics
    adc_battery_voltage = 2*(adc_reading * max_battery_voltage / max_adc_value)
    return adc_battery_voltage


def lora_set(freq_mhz):
    LORA_UART.write("AT+MODE=TEST")
    sleep_ms(1000)
    print('Lora Resp:', LORA_UART.read())
    LORA_UART.write(
        "AT+TEST=RFCFG,{},SF12,125,12,15,14,ON,OFF,OFF".format(freq_mhz))
    sleep_ms(1000)
    print('Lora Resp:', LORA_UART.read())


def lora_data_receive():
    LORA_UART.write('AT+TEST=RXLRPKT')
    sleep_ms(500)
    print('Lora RX:', LORA_UART.read())

def is_hex_ascii_convertible(hex_string):
    if not all(c in '0123456789abcdefABCDEF' for c in hex_string):
        return False

    if len(hex_string) % 2 != 0:
        return False

    try:
        decoded_bytes = bytes(int(hex_string[i:i+2], 16) for i in range(0, len(hex_string), 2))
    except ValueError:
        return False

    return all(32 <= byte <= 126 for byte in decoded_bytes)

def parse_lora_module_message(message):
    # expected packet like: '+TEST: LEN:31, RSSI:-35, SNR:12\r\n+TEST: RX \"30302C3030302C35302E3531313732352C33302E3739313934352C33393936\"\r\n'
    line = str(message).split(" ")
    if len(line) > 2 and line[-2] == 'RX':
        received_data = line[-1][1:]
        end_hex_data_pos = received_data.find('\"')
        if end_hex_data_pos != -1:
            received_data = received_data[0:end_hex_data_pos]
            return received_data
    return None


def parse_loko_string_packet(string, key):
    values = string.split(',')
    print(values)
    if len(values) == 5:
        # message : '123,321,40.376123,49.850848,3420'
        id1 = int(values[0])
        id2 = int(values[1])

        # do not use float() result will round to five digit, ex: 50.511725 >>>> 50.51172 and 30.791945 >>>> 30.79195
        lat = (values[2])
        lon = (values[3])

        vbat = int(values[4])
        return {'id1': id1, 'id2': id2, 'lat': lat, 'lon': lon, 'vbat': vbat}
    if len(values) == 7:
        # message : '00,000,54.685349,25.282091,117,0,6432'
        id1 = int(values[0])
        id2 = int(values[1])

        # do not use float() result will round to five digit, ex: 50.511725 >>>> 50.51172 and 30.791945 >>>> 30.79195
        lat = (values[2])
        lon = (values[3])
        alt_meters = int(values[4])
        meters_per_second = int(values[5])

        vbat = int(values[6])
        return {'id1': id1, 'id2': id2, 'lat': lat, 'lon': lon, 'vbat': vbat, 'alt': alt_meters, 'mps': meters_per_second}
    if len(values) == 3:
        # message :'00,000,KsC72EMf5cAYJU8eATDTMg=='
        id1 = int(values[0])
        id2 = int(values[1])
        base64 = values[2]
        encrypted_bytes = ubinascii.a2b_base64(base64)

        # Initialize the AES cipher in ECB mode
        cipher = aes(key, 1)  # 1 for ECB mode
        decrypted_bytes = cipher.decrypt(encrypted_bytes)
        checksum = sum(decrypted_bytes[:-1]) % 256
        lat, lon, vbat_mv, alt_meters, speed_mps, reserved1, integrity= struct.unpack('<ffHHHBB', decrypted_bytes)
        if checksum == integrity:
            return {'id1': id1, 'id2': id2, 'lat': lat, 'lon': lon, 'vbat': vbat_mv, 'alt': alt_meters, 'mps': speed_mps}
        else:
            print('Can\'t decrypt, possible wrong key')

    return None

def bin_unpack_vbat(vbat):
    return (vbat + 27) * 0.1

def bin_unpack_lat_lon(packed_data):
    # Extract and convert 3 bytes for latitude to a signed 24-bit integer
    lat_lon_scaled = (packed_data[0] << 16) | (packed_data[1] << 8) | packed_data[2]
    if lat_lon_scaled & 0x800000:  # Check if the sign bit is set for a negative value
        lat_lon_scaled -= 0x1000000  # Convert to signed 24-bit integer

    scaling_factor = 10000.0
    lat_lon = lat_lon_scaled / scaling_factor

    return lat_lon

def parse_loko_bin_packet(bin_data, key):
    id1 = 0
    id2 = 0
    vbat_mv = 0
    packet_version = 0
    lat = 0.0
    lon = 0.0
    alt_meters = 0
    speed_mps = 0
    data = bytes(int(bin_data[i:i+2], 16) for i in range(0, len(bin_data), 2))
    if len(data) == 15:
        id1, id2, vb_version, lat_24bit, lon_24bit= struct.unpack("<IIB3s3s", data)
        packet_version = (vb_version >> 4) & 0x0F
        vbat_mv = bin_unpack_vbat(vb_version & 0x0F)
        lat = bin_unpack_lat_lon(lat_24bit)
        lon = bin_unpack_lat_lon(lon_24bit)
    elif len(data) == 18:
        id1, id2, vb_version, lat_24bit, lon_24bit, speed_mps, alt_meters= struct.unpack("<IIB3s3sBh", data)
        packet_version = (vb_version >> 4) & 0x0F
        vbat_mv = bin_unpack_vbat(vb_version & 0x0F)
        lat = bin_unpack_lat_lon(lat_24bit)
        lon = bin_unpack_lat_lon(lon_24bit)
    elif len(data) == 25:
        id1, id2, vb_version, aes_payload= struct.unpack(">IIB16s", data)
        packet_version = (vb_version >> 4) & 0x0F
        encrypted_bytes = bytes(aes_payload)

        # Initialize the AES cipher in ECB mode
        cipher = aes(key, 1)  # 1 for ECB mode
        # cipher = AES.new(key, AES.MODE_ECB)
        decrypted_bytes = cipher.decrypt(encrypted_bytes)
        checksum = sum(decrypted_bytes[:-1]) % 256

        (vb_version, lat_24bit, lon_24bit, speed_mps, alt_meters, reserved1,  integrity) = struct.unpack('<B3s3sBH5sB', decrypted_bytes)
        if checksum != integrity:
            print('Can\'t decrypt, possible wrong key')
        else:
            vbat_mv = bin_unpack_vbat(vb_version & 0x0F)
            lat = bin_unpack_lat_lon(lat_24bit)
            lon = bin_unpack_lat_lon(lon_24bit)

    return {'id1': id1, 'id2': id2, 'lat': lat, 'lon': lon, 'vbat': vbat_mv, 'alt': alt_meters, 'mps': speed_mps}

def button_timer(pin):
    print('Power value:', POWER_CTRL.value())
    if BUTTON.value() == 0:
        print("counting till 3")
        sleep_ms(2000)
        if BUTTON.value() == 0:
            LED_RED.value(not LED_GREEN.value())
            POWER_CTRL.value(not POWER_CTRL.value())
            print('Power value:', POWER_CTRL.value())
        else:
            print('Button released')


def main():
    print (battery_level())

    LED_BLUE.value(0)
    sleep_ms(500)

    LED_BLUE.value(1)
    LED_RED.value(0)
    sleep_ms(500)

    LED_RED.value(1)
    LED_GREEN.value(0)
    sleep_ms(500)

    LED_GREEN.value(1)
    POWER_CTRL.value(1)
    LED_GREEN.value(0)
    sleep_ms(500)

    LED_GREEN.value(1)

    settings = SETTINGS()
    if use_coommand_line_parser == True:
        command_parser = COMMAND_RECEIVER(settings)

    key = bytes(int(settings.data['p2p_key'][i:i+2], 16) for i in range(0, len(settings.data['p2p_key']), 2))
    
    BUTTON.irq(trigger=Pin.IRQ_FALLING, handler=button_timer)
    ble = LOKO_BLE("LOKO")
    lora_set(settings.data['freq'])
    lora_data_receive()
    btCounter = 0

    # battery_level()
    
    while True:
        
        sleep_ms(100)
        
        if battery_level() < 3.3:
            print("Battery level too low. Device entering deep sleep to protect from overcharge.")
            # Enter deep sleep mode indefinitely
            sleep_ms(100)
            POWER_CTRL.value(0)
        

        if use_coommand_line_parser == True:
            if command_parser.exit_request == True:
               sys.exit(1)
               
        if (btCounter < 301):
            if ble.is_connected:
                btr = (battery_level() - 3.3) * 100/0.9
                batterStr = str(round(btr,2))
                ble.send(batterStr)
        btCounter = btCounter + 1
        if(btCounter > 300):
            btCounter = 0

        lora_data = LORA_UART.read()
        if lora_data == None:
            continue
        print('LoraRx: ', lora_data)

        loko_payload = parse_lora_module_message(lora_data)
        if loko_payload == None:
            continue
        loko_data = None
        loko_string = ""
        if is_hex_ascii_convertible(loko_payload):
            converted_data = ubinascii.unhexlify(loko_payload)
            loko_string = converted_data.decode("utf-8")
            print('LokoMessage: ', loko_string)

            loko_data = parse_loko_string_packet(loko_string, key)
        else:
            loko_data = parse_loko_bin_packet(loko_payload, key)
            loko_string =  f'{loko_data["id1"]},{loko_data["id2"]},{loko_data["lat"]},{loko_data["lon"]},{loko_data["vbat"]},{loko_data["alt"]},{loko_data["mps"]}'
            sleep_ms(100)
            print('LokoMessage: ', loko_string)
        if loko_data != None:
            if loko_data['id2'] == settings.data['id2']:
                if ble.is_connected:
                    ble.send(loko_string)
                else:
                    print('BLE not connected')
            else:
                print('DEBUG:Received unexpected ID2={}, Expected={}'.format(
                    loko_data['id2'], settings.data['id2']))

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Ctrl+C pressed, exit from application')
        exit(1)



