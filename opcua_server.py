#!/usr/bin/env python3
"""
Industrial IoT OPC UA Server
Author: Shah Mohammed Tahmid
Description: OPC UA server exposing DHT11, INA219, and HC-SR04 sensor data
for industrial SCADA integration

Requirements:
    pip3 install asyncua
    pip3 install adafruit-circuitpython-dht
    pip3 install adafruit-circuitpython-ina219
    pip3 install RPi.GPIO

OPC UA Server Details:
    Endpoint: opc.tcp://0.0.0.0:4840/freeopcua/server/
    Namespace: http://iot.stonybrook.edu
    
Connect with UAExpert or any OPC UA client to view live sensor data
"""

import asyncio
import logging
import sys
from datetime import datetime

# OPC UA imports
try:
    from asyncua import Server, ua
    from asyncua.common.methods import uamethod
except ImportError:
    print("Error: asyncua not installed")
    print("Install with: pip3 install asyncua")
    sys.exit(1)

# Sensor imports
try:
    import board
    import adafruit_dht
    from adafruit_ina219 import INA219
    import busio
    import RPi.GPIO as GPIO
except ImportError as e:
    print(f"Error: Missing sensor library - {e}")
    print("Install with: pip3 install adafruit-circuitpython-dht adafruit-circuitpython-ina219 RPi.GPIO")
    sys.exit(1)

import time

# Configure logging
logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger('opcua.server')

# GPIO Pin Configuration
DHT_PIN = board.D4          # DHT11 data pin (GPIO 4)
TRIG_PIN = 23               # HC-SR04 trigger pin
ECHO_PIN = 24               # HC-SR04 echo pin

# Server Configuration
SERVER_ENDPOINT = "opc.tcp://0.0.0.0:4840/freeopcua/server/"
SERVER_NAME = "Industrial IoT Sensor Server"
NAMESPACE_URI = "http://iot.stonybrook.edu"

# Update interval (seconds)
UPDATE_INTERVAL = 2.0


class SensorReader:
    """Class to handle all sensor reading operations"""
    
    def __init__(self):
        """Initialize all sensors"""
        _logger.info("Initializing sensors...")
        
        # Initialize DHT11
        try:
            self.dht_sensor = adafruit_dht.DHT11(DHT_PIN)
            _logger.info("✓ DHT11 initialized")
        except Exception as e:
            _logger.error(f"✗ DHT11 initialization failed: {e}")
            self.dht_sensor = None
        
        # Initialize INA219
        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            self.ina219 = INA219(i2c)
            _logger.info("✓ INA219 initialized")
        except Exception as e:
            _logger.error(f"✗ INA219 initialization failed: {e}")
            self.ina219 = None
        
        # Initialize HC-SR04
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            GPIO.setup(TRIG_PIN, GPIO.OUT)
            GPIO.setup(ECHO_PIN, GPIO.IN)
            GPIO.output(TRIG_PIN, False)
            time.sleep(0.5)  # Let sensor settle
            _logger.info("✓ HC-SR04 initialized")
            self.ultrasonic_enabled = True
        except Exception as e:
            _logger.error(f"✗ HC-SR04 initialization failed: {e}")
            self.ultrasonic_enabled = False
    
    def read_dht11(self):
        """
        Read temperature and humidity from DHT11
        Returns: (temperature_c, humidity, status_code)
        """
        if not self.dht_sensor:
            return 0.0, 0.0, 2  # Status 2 = Sensor error
        
        try:
            temperature_c = self.dht_sensor.temperature
            humidity = self.dht_sensor.humidity
            
            if temperature_c is not None and humidity is not None:
                return float(temperature_c), float(humidity), 0  # Status 0 = OK
            else:
                return 0.0, 0.0, 1  # Status 1 = Read error
                
        except RuntimeError:
            # DHT11 timeout - common, not critical
            return 0.0, 0.0, 1
        except Exception as e:
            _logger.error(f"DHT11 error: {e}")
            return 0.0, 0.0, 2
    
    def read_ina219(self):
        """
        Read voltage, current, and power from INA219
        Returns: (voltage, current, power, status_code)
        """
        if not self.ina219:
            return 0.0, 0.0, 0.0, 2  # Status 2 = Sensor error
        
        try:
            voltage = self.ina219.bus_voltage  # V
            current = self.ina219.current / 1000.0  # Convert mA to A
            power = self.ina219.power / 1000.0  # Convert mW to W
            
            return float(voltage), float(current), float(power), 0  # Status 0 = OK
            
        except Exception as e:
            _logger.error(f"INA219 error: {e}")
            return 0.0, 0.0, 0.0, 2
    
    def read_ultrasonic(self):
        """
        Read distance from HC-SR04 ultrasonic sensor
        Returns: (distance_cm, status_code)
        """
        if not self.ultrasonic_enabled:
            return 0.0, 2  # Status 2 = Sensor error
        
        try:
            # Send trigger pulse
            GPIO.output(TRIG_PIN, True)
            time.sleep(0.00001)  # 10 microseconds
            GPIO.output(TRIG_PIN, False)
            
            # Measure echo pulse duration with timeout
            timeout_start = time.time()
            pulse_start = timeout_start
            
            while GPIO.input(ECHO_PIN) == 0:
                pulse_start = time.time()
                if pulse_start - timeout_start > 0.1:  # 100ms timeout
                    return 0.0, 1  # Status 1 = Timeout
            
            pulse_end = pulse_start
            while GPIO.input(ECHO_PIN) == 1:
                pulse_end = time.time()
                if pulse_end - pulse_start > 0.1:
                    return 0.0, 1
            
            # Calculate distance (speed of sound = 343 m/s)
            pulse_duration = pulse_end - pulse_start
            distance = pulse_duration * 17150  # (343m/s * 100cm/m) / 2
            distance = round(distance, 2)
            
            # Validate reading (sensor range: 2-400cm)
            if 2 <= distance <= 400:
                return float(distance), 0  # Status 0 = OK
            else:
                return 0.0, 3  # Status 3 = Out of range
                
        except Exception as e:
            _logger.error(f"HC-SR04 error: {e}")
            return 0.0, 2
    
    def cleanup(self):
        """Clean up GPIO resources"""
        if self.dht_sensor:
            self.dht_sensor.exit()
        if self.ultrasonic_enabled:
            GPIO.cleanup()


class OPCUAServer:
    """OPC UA Server managing sensor data"""
    
    def __init__(self):
        self.server = None
        self.sensor_reader = SensorReader()
        self.nodes = {}
        
    async def init_server(self):
        """Initialize OPC UA server and create address space"""
        
        # Create server instance
        self.server = Server()
        await self.server.init()
        
        # Configure server
        self.server.set_endpoint(SERVER_ENDPOINT)
        self.server.set_server_name(SERVER_NAME)
        
        # Set security policy (None for development - use encryption in production!)
        self.server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
        
        # Setup namespace
        uri = NAMESPACE_URI
        idx = await self.server.register_namespace(uri)
        
        _logger.info(f"Namespace index: {idx}")
        _logger.info(f"Server endpoint: {SERVER_ENDPOINT}")
        
        # Get Objects node
        objects = self.server.get_objects_node()
        
        # Create main sensor folder
        sensor_folder = await objects.add_folder(idx, "SensorData")
        
        # Create DHT11 sensor object
        dht11_obj = await sensor_folder.add_object(idx, "DHT11_Sensor")
        self.nodes['temp'] = await dht11_obj.add_variable(
            idx, "Temperature_C", 0.0
        )
        self.nodes['temp_f'] = await dht11_obj.add_variable(
            idx, "Temperature_F", 0.0
        )
        self.nodes['humidity'] = await dht11_obj.add_variable(
            idx, "Humidity_Percent", 0.0
        )
        self.nodes['dht_status'] = await dht11_obj.add_variable(
            idx, "Status", 0
        )
        
        # Create INA219 sensor object
        ina219_obj = await sensor_folder.add_object(idx, "INA219_PowerMonitor")
        self.nodes['voltage'] = await ina219_obj.add_variable(
            idx, "Voltage_V", 0.0
        )
        self.nodes['current'] = await ina219_obj.add_variable(
            idx, "Current_A", 0.0
        )
        self.nodes['power'] = await ina219_obj.add_variable(
            idx, "Power_W", 0.0
        )
        self.nodes['ina_status'] = await ina219_obj.add_variable(
            idx, "Status", 0
        )
        
        # Create HC-SR04 sensor object
        ultrasonic_obj = await sensor_folder.add_object(idx, "HCSR04_Distance")
        self.nodes['distance'] = await ultrasonic_obj.add_variable(
            idx, "Distance_cm", 0.0
        )
        self.nodes['distance_in'] = await ultrasonic_obj.add_variable(
            idx, "Distance_inches", 0.0
        )
        self.nodes['ultrasonic_status'] = await ultrasonic_obj.add_variable(
            idx, "Status", 0
        )
        
        # Create system status object
        system_obj = await sensor_folder.add_object(idx, "SystemInfo")
        self.nodes['timestamp'] = await system_obj.add_variable(
            idx, "LastUpdate", ""
        )
        self.nodes['uptime'] = await system_obj.add_variable(
            idx, "Uptime_seconds", 0.0
        )
        
        # Make all variables writable for testing purposes
        for node in self.nodes.values():
            await node.set_writable()
        
        _logger.info("✓ OPC UA address space created")
        _logger.info(f"  - DHT11 variables: Temperature_C, Temperature_F, Humidity_Percent")
        _logger.info(f"  - INA219 variables: Voltage_V, Current_A, Power_W")
        _logger.info(f"  - HC-SR04 variables: Distance_cm, Distance_inches")
        
        return idx
    
    async def update_values(self, start_time):
        """Read sensors and update OPC UA variables"""
        
        # Read all sensors
        temp_c, humidity, dht_status = self.sensor_reader.read_dht11()
        voltage, current, power, ina_status = self.sensor_reader.read_ina219()
        distance_cm, ultrasonic_status = self.sensor_reader.read_ultrasonic()
        
        # Calculate derived values
        temp_f = temp_c * 9.0/5.0 + 32.0
        distance_in = distance_cm / 2.54
        uptime = time.time() - start_time
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Update DHT11 values
        await self.nodes['temp'].write_value(temp_c)
        await self.nodes['temp_f'].write_value(temp_f)
        await self.nodes['humidity'].write_value(humidity)
        await self.nodes['dht_status'].write_value(dht_status)
        
        # Update INA219 values
        await self.nodes['voltage'].write_value(voltage)
        await self.nodes['current'].write_value(current)
        await self.nodes['power'].write_value(power)
        await self.nodes['ina_status'].write_value(ina_status)
        
        # Update HC-SR04 values
        await self.nodes['distance'].write_value(distance_cm)
        await self.nodes['distance_in'].write_value(distance_in)
        await self.nodes['ultrasonic_status'].write_value(ultrasonic_status)
        
        # Update system info
        await self.nodes['timestamp'].write_value(timestamp)
        await self.nodes['uptime'].write_value(uptime)
        
        # Log to console
        _logger.info(f"Updated: Temp={temp_c:.1f}°C, Humidity={humidity:.1f}%, "
                    f"Voltage={voltage:.2f}V, Current={current:.3f}A, "
                    f"Distance={distance_cm:.1f}cm")
    
    async def run(self):
        """Start OPC UA server and update loop"""
        try:
            # Initialize server
            await self.init_server()
            
            # Start server
            async with self.server:
                _logger.info("=" * 60)
                _logger.info("OPC UA Server Started Successfully!")
                _logger.info("=" * 60)
                _logger.info(f"Endpoint: {SERVER_ENDPOINT}")
                _logger.info(f"Connect with UAExpert or any OPC UA client")
                _logger.info(f"Update interval: {UPDATE_INTERVAL}s")
                _logger.info("Press CTRL+C to stop")
                _logger.info("=" * 60)
                
                start_time = time.time()
                
                # Main update loop
                while True:
                    await self.update_values(start_time)
                    await asyncio.sleep(UPDATE_INTERVAL)
                    
        except KeyboardInterrupt:
            _logger.info("\nShutdown requested...")
        except Exception as e:
            _logger.error(f"Server error: {e}", exc_info=True)
        finally:
            _logger.info("Cleaning up sensors...")
            self.sensor_reader.cleanup()
            _logger.info("Server stopped")


async def main():
    """Main entry point"""
    opcua_server = OPCUAServer()
    await opcua_server.run()


if __name__ == "__main__":
    asyncio.run(main())
