import machine
from machine import Pin,UART,Timer,ADC
from time import sleep, sleep_ms
import utime, time
import ubinascii
import ubluetooth


# adc = ADC(0)          # create ADC object on ADC pin
# 
# 
# def battery_level():
#     #adc.atten(ADC.ATTN_11DB)    # set 11dB input attenuation (voltage range roughly 0.0v - 3.6v)
#     #adc.width(ADC.WIDTH_9BIT)   # set 9 bit return values (returned range 0-511)
# 
#     adc_battery_gnd = adc.read()
#     
#     
#     print(adc_battery_gnd)
#     return(adc_battery_gnd)
# 
# 
# ble_msg = ""
# is_ble_connected = False


#LED=Pin(2,Pin.OUT)

Lora = UART(2, 9600) #uart2

class LOKO_BLE():
    def __init__(self, name):
        # Create internal objects for the onboard LED
        # blinking when no BLE device is connected
        # stable ON when connected
        self.led = Pin(2, Pin.OUT)
        self.timer1 = Timer(0)
        
        self.name = name
        self.ble = ubluetooth.BLE()
        self.ble.active(True)
        self.disconnected()
        self.ble.irq(self.ble_irq)
        self.register()
        self.advertiser()
        self.ble.config(gap_name="Loko")

    def connected(self):
        global is_ble_connected
        is_ble_connected = True
        self.led.value(1)
        self.timer1.deinit()

    def disconnected(self):
        global is_ble_connected
        is_ble_connected = False
        self.timer1.init(period=100, mode=Timer.PERIODIC, callback=lambda t: self.led.value(not self.led.value()))

    def ble_irq(self, event, data):
        global ble_msg
        
        if event == 1: #_IRQ_CENTRAL_CONNECT:
                       # A central has connected to this peripheral
            self.connected()

        elif event == 2: #_IRQ_CENTRAL_DISCONNECT:
                         # A central has disconnected from this peripheral.
            self.advertiser()
            self.disconnected()
        
        elif event == 3: #_IRQ_GATTS_WRITE:
                         # A client has written to this characteristic or descriptor.          
            buffer = self.ble.gatts_read(self.rx)
            ble_msg = buffer.decode('UTF-8').strip()
            
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
        self.ble.gatts_notify(0, self.tx, data + '\n')

    def advertiser(self):
        name = bytes(self.name, 'UTF-8')
        adv_data = bytearray('\x02\x01\x02') + bytearray((len(name) + 1, 0x09)) + name
        self.ble.gap_advertise(100, adv_data)
        print(adv_data)
        print("\r\n")
 




def lora_set():
    Lora.write("AT+MODE=TEST")
    sleep(1)
    print(Lora.read())
    Lora.write("AT+TEST=RFCFG,868,SF7,125,12,15,8,ON,OFF,OFF") 
    sleep(1)
    print(Lora.read())
    
def lora_data_receive():
    Lora.write('AT+TEST=RXLRPKT')
    sleep(0.5)
    print(Lora.read())
    
    
def pharse_message(message):
    line=str(message)

    line=line.split(" ")
    #print(line)
    if line==['None']:
        
        return('no Signal')
        
    else:

        if line[-2]=='RX':
            received_data=line[-1][1:-6]
            converted_data=ubinascii.unhexlify(received_data)
            a=converted_data.decode("utf-8")  # decode data
            Longitude= a[7:17]
            Long=int(a[7:9])+float(a[9:16])/60
            Latitude= a[17:27]
            Lat=int(a[17:19])+float(a[19:26])/60
            Altitude=a[27:]
            Time= a[:6]
            #ble_message= str("Id:Loko1"+"RSSI:"+RSSI+"Time: "+Time+"Lattitude:"+Latitude+"Longitude:"+Longitude+"Altitude:"+Altitude)
            ble_message= str("Id:Loko1"+" Lattitude:"+str(Lat)+" Longitude:"+str(Long)+" Altitude:"+Altitude+" Battery:70"+" RSSI:-17")

            #print(Long)
            #print(Lat)
            
            return ble_message
            #return "Time: "+Time+" Latitude: "+Latitude+" Longitude: "+Longitude+" Altitude: "+Altitude
            #return {'Time':Time,"Latitude":Latitude,"Longitude":Longitude,"Altitude":altitude}
        
        else:
            #print("no data")
            return('no data')
                      
ble = LOKO_BLE("LOCO")   
lora_set()
lora_data_receive()
#battery_level()
   
while True:
    #battery_level()
    sleep_ms(500)
   
    print(Lora.read())
    
#     #print(pharse_message(Lora.read()))
#    if is_ble_connected:
#         #sleep_ms(5000)
#         #pharse_message(Lora.read())
   # read=pharse_message(Lora.read())
   # print(read)
#         ble.send(read)
#         #ble.send(battery_level())

        



