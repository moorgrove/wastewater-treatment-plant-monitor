import pycom
import time
import _thread
import socket
import ubinascii
import ustruct
import keys
from machine import Pin
from dht import DHT # https://github.com/JurassicPork/DHT_PyCom
from onewire import DS18X20, OneWire
from network import LoRa


# Turn off led heartbeat.
pycom.heartbeat(False)

# Define sensor pins.
pinOneWire = 'P9'
pinAmbientTempHumidity = 'P23'
pinFlocculationFluidLevel = 'P11'

# Initialize DS18X20 air pump temperature sensors.
oneWire = OneWire(Pin(pinOneWire))
time.sleep(1)
oneWireSensors = oneWire.scan()
airPumpTemp = DS18X20(oneWire)
print('OneWire scan', oneWireSensors)

# Initialize DHT 11 Ambient Temperature and humidity sensors.
ambientTempHumidity = DHT(Pin(pinAmbientTempHumidity, mode=Pin.OPEN_DRAIN), 0)

# Initialize Flocculation fluid level.
flocculationFluidLevel = Pin(pinFlocculationFluidLevel, mode=Pin.IN, pull=Pin.PULL_DOWN)


# Define global varibles
airPumpsTempValue = dict()
ambientTempValue = None
ambientHumidityValue = None
lora = None
flocculationFluidLevelValue = 0

# Functon to Read DHT11
def readAmbientTempHumidity():
    # Sleep to let the sensor establish connection.
    time.sleep(2)
    # Define global variables.
    global ambientTempValue
    global ambientHumidityValue
    while True:
        # Read the sensors values.
        ambientTempHumidityResult = ambientTempHumidity.read()
        # If sensor values is not valid.
        while not ambientTempHumidityResult.is_valid():
            # Sleep 500 milliseconds.
            time.sleep(.5)
            # Do new atempt to read the sensor values.
            ambientTempHumidityResult = ambientTempHumidity.read()
        # Breakout temperature and humidity to own variables.
        ambientTempValue = ambientTempHumidityResult.temperature
        ambientHumidityValue = ambientTempHumidityResult.humidity
        # Sleep 5 seconds before new readout is performed again.
        time.sleep(5)

# Function to read Air pumps
def readAirPumpTemp():
    # Define global variables.
    global airPumpsTempValue
    # If no sensor is connected at startup, display error message.
    if not oneWireSensors:
        print('Error - No air pump temp found')
    while True:
        # For all sensors in onewire sensors.
        for oneWireSensor in oneWireSensors:
            # Initialize communication with onewire sensors.
            airPumpTemp.start_conversion(oneWireSensor)
            # Sleep to let the onewire communicate with the sensor.
            time.sleep(1)
            # Read sensor value.
            airPumpTempValue = round(airPumpTemp.read_temp_async(oneWireSensor), 1)
            # If sensor gets disconnected is states value -0.1.
            if airPumpTempValue == -0.1:
                # Store 'none' if sensor get invalid data.
                airPumpsTempValue[str(oneWireSensor)] = None
            else:
                # Store sensor data in dictionary.
                airPumpsTempValue[str(oneWireSensor)] = airPumpTempValue

# Function to read flocculation fluid level
def readFlocLevel():
    while True:
        # Define global variables.
        global flocculationFluidLevelValue
        # Store values of function in varaiable.
        flocculationFluidLevelValue = flocculationFluidLevel()
        # If flocculationFluidLevel gets no signal, level is to low. Then activate red led, else turn off the led.
        if flocculationFluidLevel() == 0:
            pycom.rgbled(0xFF0000)
        else:
            pycom.rgbled(0x000000)
        # Sleep 500 milliseconds before now readout is performed.
        time.sleep(0.5)

# Function to join LoraWAN network
def joinLoraWan():
    # Define global variable.
    global lora
    # Initialise LoRa in LORAWAN mode.
    lora = LoRa(mode=LoRa.LORAWAN, region=LoRa.EU868)
    # Create an OTAA authentication parameters, change them to the provided credentials in keys.py.
    app_eui = ubinascii.unhexlify(keys.lora_app_eui)
    app_key = ubinascii.unhexlify(keys.lora_app_key)
    dev_eui = ubinascii.unhexlify(keys.lora_dev_eui)
    # Join a network using OTAA (Over the Air Activation).
    lora.join(activation=LoRa.OTAA, auth=(dev_eui, app_eui, app_key), timeout=0)

# Function to send data with LoraWAN.
def sendDataLoraWan():
    # Sleep 5 seconds to first perform join function.
    time.sleep(5)
    # Define global variables.
    global lora
    # Wait until the module has joined the network.
    while not lora.has_joined():
        time.sleep(2.5)
        print('LoraWAN | Not yet joined')
    print('LoraWAN | Joined')

    while True:
        # Create a LoRa socket.
        s = socket.socket(socket.AF_LORA, socket.SOCK_RAW)
        # Set the LoRaWAN data rate.
        s.setsockopt(socket.SOL_LORA, socket.SO_DR, 5)
        # Make the socket blocking. Waits for the data to be sent and for the 2 receive windows to expire.
        s.setblocking(True)
        # Send the data.
        s.send(bytes([flocculationFluidLevelValue, ambientTempValue, ambientHumidityValue, int(list(airPumpsTempValue.values())[0]), int(list(airPumpsTempValue.values())[1])]))
        print('Data sent with LoraWAN')
        # Make the socket non-blocking. Because if there's no data received it will block forever.
        s.setblocking(False)
        # Get any data received.
        data = s.recv(64)
        # Pring the received data.
        print(data)
        # Sleep 30 minutes before uploading new data.
        time.sleep(1800)

# Start threads that collect sensor data.
_thread.start_new_thread(readAirPumpTemp, ())
_thread.start_new_thread(readAmbientTempHumidity,())
_thread.start_new_thread(readFlocLevel, ())

# Sleep to let the sensors collect their first value.
time.sleep(5)

# Join the LoraWan network.
_thread.start_new_thread(joinLoraWan, ())

# Start thread that sends data with LoraWAN.
_thread.start_new_thread(sendDataLoraWan, ())

# Main thread
while True:
    # Print values for debugging purpuse.
    print('Floc level:', flocculationFluidLevelValue)
    print('Ambient Temp:', ambientTempValue, '| Humidity:', ambientHumidityValue)
    print('Air pump temp:', list(airPumpsTempValue.values())[0], '|', list(airPumpsTempValue.values())[1])
    # Sleep 1 minute before values are printed again.
    time.sleep(60)
