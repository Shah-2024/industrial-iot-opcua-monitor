#!/usr/bin/env python3
"""
Sensor Testing Script
Tests each sensor individually to verify hardware connections

Run this before starting the OPC UA server to ensure all sensors work correctly.

Usage:
    python3 test_sensors.py
"""

import time
import sys

print("=" * 60)
print("INDUSTRIAL IOT SENSOR TEST SUITE")
print("=" * 60)
print("This script tests each sensor individually")
print("Press CTRL+C to stop at any time\n")

# Test 1: DHT11 Temperature/Humidity Sensor
print("[1/3] Testing DHT11 Temperature/Humidity Sensor...")
print("-" * 60)

try:
    import board
    import adafruit_dht
    
    DHT_PIN = board.D4
    dht_sensor = adafruit_dht.DHT11(DHT_PIN)
    
    print("DHT11 Configuration:")
    print(f"  Pin: GPIO 4 (board.D4)")
    print(f"  Polling: Attempting 5 readings with 3s intervals")
    print()
    
    success_count = 0
    for i in range(5):
        try:
            temperature = dht_sensor.temperature
            humidity = dht_sensor.humidity
            
            if temperature is not None and humidity is not None:
                temp_f = temperature * 9.0/5.0 + 32.0
                print(f"  Reading {i+1}: Temp = {temperature:.1f}°C ({temp_f:.1f}°F), "
                      f"Humidity = {humidity:.1f}%")
                success_count += 1
            else:
                print(f"  Reading {i+1}: Failed (null values)")
        
        except RuntimeError as e:
            print(f"  Reading {i+1}: Timeout (this is normal occasionally)")
        except Exception as e:
            print(f"  Reading {i+1}: Error - {e}")
        
        if i < 4:  # Don't sleep after last reading
            time.sleep(3.0)  # DHT11 needs 2+ seconds between readings
    
    print()
    if success_count >= 3:
        print(f"✓ DHT11 TEST PASSED ({success_count}/5 successful readings)")
    elif success_count > 0:
        print(f"⚠ DHT11 PARTIAL SUCCESS ({success_count}/5 readings)")
        print("  Tip: Add 4.7kΩ pull-up resistor between Data pin and 3.3V")
    else:
        print(f"✗ DHT11 TEST FAILED (0/5 successful readings)")
        print("  Check wiring: VCC→3.3V, Data→GPIO4, GND→GND")
    
    dht_sensor.exit()
    
except ImportError:
    print("✗ DHT11 library not installed")
    print("  Install: pip3 install adafruit-circuitpython-dht")
except Exception as e:
    print(f"✗ DHT11 initialization error: {e}")

print()
time.sleep(2)

# Test 2: INA219 Current/Voltage Sensor
print("[2/3] Testing INA219 Current/Voltage Sensor...")
print("-" * 60)

try:
    import board
    import busio
    from adafruit_ina219 import INA219
    
    i2c = busio.I2C(board.SCL, board.SDA)
    ina219 = INA219(i2c)
    
    print("INA219 Configuration:")
    print(f"  I2C Address: 0x40")
    print(f"  SDA: GPIO 2 (Pin 3)")
    print(f"  SCL: GPIO 3 (Pin 5)")
    print(f"  Taking 5 readings with 1s intervals")
    print()
    
    for i in range(5):
        try:
            bus_voltage = ina219.bus_voltage      # Voltage in V
            shunt_voltage = ina219.shunt_voltage / 1000  # Convert to V
            current = ina219.current / 1000       # Convert mA to A
            power = ina219.power / 1000           # Convert mW to W
            
            print(f"  Reading {i+1}:")
            print(f"    Bus Voltage:   {bus_voltage:.3f} V")
            print(f"    Shunt Voltage: {shunt_voltage:.6f} V")
            print(f"    Current:       {current:.4f} A")
            print(f"    Power:         {power:.4f} W")
            
        except Exception as e:
            print(f"  Reading {i+1}: Error - {e}")
        
        if i < 4:
            time.sleep(1.0)
    
    print()
    print("✓ INA219 TEST PASSED")
    print("  Note: Connect a load between VIN+ and VIN- to see non-zero current")
    
except ImportError:
    print("✗ INA219 library not installed")
    print("  Install: pip3 install adafruit-circuitpython-ina219")
except ValueError as e:
    print("✗ INA219 I2C communication error")
    print(f"  Error: {e}")
    print("  Check:")
    print("    1. I2C enabled: sudo raspi-config → Interface → I2C")
    print("    2. Device detected: sudo i2cdetect -y 1 (should show 0x40)")
    print("    3. Wiring: SDA→Pin3, SCL→Pin5, VCC→3.3V, GND→GND")
except Exception as e:
    print(f"✗ INA219 initialization error: {e}")

print()
time.sleep(2)

# Test 3: HC-SR04 Ultrasonic Distance Sensor
print("[3/3] Testing HC-SR04 Ultrasonic Distance Sensor...")
print("-" * 60)

try:
    import RPi.GPIO as GPIO
    
    TRIG_PIN = 23
    ECHO_PIN = 24
    
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(TRIG_PIN, GPIO.OUT)
    GPIO.setup(ECHO_PIN, GPIO.IN)
    GPIO.output(TRIG_PIN, False)
    
    print("HC-SR04 Configuration:")
    print(f"  Trigger Pin: GPIO 23 (Pin 16)")
    print(f"  Echo Pin:    GPIO 24 (Pin 18) - ⚠️ MUST use voltage divider!")
    print(f"  Range:       2-400 cm")
    print(f"  Taking 5 readings with 1s intervals")
    print()
    
    time.sleep(0.5)  # Let sensor settle
    
    success_count = 0
    distances = []
    
    for i in range(5):
        try:
            # Send trigger pulse
            GPIO.output(TRIG_PIN, True)
            time.sleep(0.00001)  # 10 microseconds
            GPIO.output(TRIG_PIN, False)
            
            # Measure echo pulse
            timeout_start = time.time()
            pulse_start = timeout_start
            
            while GPIO.input(ECHO_PIN) == 0:
                pulse_start = time.time()
                if pulse_start - timeout_start > 0.1:  # 100ms timeout
                    raise TimeoutError("No echo received (start)")
            
            pulse_end = pulse_start
            while GPIO.input(ECHO_PIN) == 1:
                pulse_end = time.time()
                if pulse_end - pulse_start > 0.1:
                    raise TimeoutError("No echo received (end)")
            
            # Calculate distance
            pulse_duration = pulse_end - pulse_start
            distance = pulse_duration * 17150  # Speed of sound / 2
            distance = round(distance, 2)
            
            # Validate reading
            if 2 <= distance <= 400:
                distance_in = distance / 2.54
                print(f"  Reading {i+1}: {distance:.1f} cm ({distance_in:.1f} inches) ✓")
                distances.append(distance)
                success_count += 1
            else:
                print(f"  Reading {i+1}: {distance:.1f} cm - OUT OF RANGE (2-400cm)")
        
        except TimeoutError as e:
            print(f"  Reading {i+1}: Timeout - {e}")
        except Exception as e:
            print(f"  Reading {i+1}: Error - {e}")
        
        if i < 4:
            time.sleep(1.0)
    
    print()
    if success_count >= 3:
        avg_distance = sum(distances) / len(distances)
        std_dev = (sum((x - avg_distance)**2 for x in distances) / len(distances))**0.5
        print(f"✓ HC-SR04 TEST PASSED ({success_count}/5 successful readings)")
        print(f"  Average distance: {avg_distance:.1f} cm")
        print(f"  Std deviation:    {std_dev:.1f} cm")
        
        if std_dev > 5.0:
            print("  ⚠ High variance detected - check for:")
            print("    - Vibrations or air currents")
            print("    - Unstable mounting")
            print("    - Reflective surfaces nearby")
    else:
        print(f"✗ HC-SR04 TEST FAILED ({success_count}/5 successful readings)")
        print("  Common issues:")
        print("    1. No voltage divider on Echo pin (will damage RPi!)")
        print("       Required: Echo → 1kΩ → GPIO24 → 2kΩ → GND")
        print("    2. Insufficient power (needs stable 5V)")
        print("    3. Object too close (<2cm) or too far (>400cm)")
        print("    4. Wiring: VCC→5V, Trig→GPIO23, Echo→GPIO24(divider), GND→GND")
    
    GPIO.cleanup()
    
except ImportError:
    print("✗ RPi.GPIO library not installed")
    print("  Install: pip3 install RPi.GPIO")
except Exception as e:
    print(f"✗ HC-SR04 initialization error: {e}")
    GPIO.cleanup()

# Final Summary
print()
print("=" * 60)
print("TEST SUITE COMPLETE")
print("=" * 60)
print()
print("Next Steps:")
print("  1. If all tests passed → Run OPC UA server: python3 opcua_server.py")
print("  2. If tests failed → Fix wiring/configuration issues above")
print("  3. Connect UAExpert client to: opc.tcp://<RPi_IP>:4840")
print()
print("For detailed troubleshooting, see README.md")
print("=" * 60)