#!/usr/bin/env python3

import serial, sys, os, time, logging, datetime, json, methods, asyncio
from serial import SerialException
import serial.tools.list_ports
from sys import platform
from logging.handlers import TimedRotatingFileHandler
from methods import read_data, write_data, loadConfig
from command import *
# ------------------------------------------------------------------------------------------------------------
# DEFINITIONS AND INITIALISATIONS

if platform == "linux":
   dir = "/data/opt/LEDMonitoring"
else:
   dir = r"C:\LEDMonitoring"
os.chdir(dir)

# LOGGER
FORMATTER = logging.Formatter('%(asctime)s %(name)s %(levelname)-8s %(message)s', datefmt='%d/%m/%Y %H:%M:%S')
STATUS_FILE = "status.json"
LOGGER_SCHEDULE = 'midnight'
LOGGER_BACKUPS = 7
LOGGER_INTERVAL = 1
LOGGER_NAME = "display_status"
LOG_FILE = "debug.log" 
MODEL_6XX = "MSD600/MCTRL600/MCTRL610/MCTRL660"

# EXIT CODES
GOOD = 0
WARNING = 1
CRITICAL = 2
UNKNOWN = 3

async def communicate_with_server(callback, check_name):
   global data
   global logger
   logger = methods.get_logger(check_name,LOG_FILE,FORMATTER,LOGGER_SCHEDULE,LOGGER_INTERVAL,LOGGER_BACKUPS) # Set up the logging  
   logger.info("ESTABLISHING CONNECTION WITH LOCAL SERVER QUEUE")
   reader, writer = await asyncio.open_connection("127.0.0.1",8888)
   if not reader and not writer:
      logger.error("COULD NOT ESTABLISH CONNECTION WITH 127.0.0.1 ON PORT 8888")
   writer.write(f"{check_name}".encode())
   await writer.drain()
   logger.info("AWAITING PERMISSION TO USE COM PORTS FROM LOCAL SERVER")
   data = await reader.read(1024)
   if not data.decode().strip() == "START":
      logger.error("Could not make connection with localserver to access com port")
      session_handler(writer,reader)
      exit()
   logger.info(f"PERMISSION TO USE COM PORT GRANTED STARTING {check_name} SCRIPT")
   await callback(reader, writer) #callback is the method passed to run after permission is granted   
async def initialize_program(reader, writer):
   global sleep_time
   global flash_wait_time
   global status 
   global last_updated
   global data
   global logger
   global config
   module_status_info = {}
   my_logger = methods.get_logger(LOGGER_NAME,LOG_FILE,FORMATTER,LOGGER_SCHEDULE,LOGGER_INTERVAL,LOGGER_BACKUPS) # Set up the logging
   my_logger.info("*********************************************************************************************************************************************")
   my_logger.info("5Eyes - Starting Display Status Checks")
   config = loadConfig(LOGGER_NAME) # Load the configuration information
   my_logger.info("Version: {}, Baudrate: {}, Sleep Time: {}, Flash Timeout: {}".format(config["version"],config["baudrate"],config["sleepTime"],config["flashWaitTime"]))
   last_updated = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
   sleep_time = float(config["sleepTime"])
   flash_wait_time = float(config["flashWaitTime"])
   data = read_data(STATUS_FILE,LOGGER_NAME)
   status = {} # Initialise variable to store status data\
   modules_ok = True # assume all modules are ok to start off
   number_of_modules = config["modules"]
   ser = methods.setupSerialPort(config["baudrate"],LOGGER_NAME) # Initialise serial port
   device_found, valid_ports = search_devices(ser)
   start_time = time.time()
      #Validate device found on player
   if not valid_ports:
      message = "NO DEVICE - make sure a valid controller is connected, that the correct baudrate is defined in config.json and ensure the NOVA LCT is not running on the host system \nThis can also mean that you don't run the tool as administrator"
      exit_code = CRITICAL
      logger.info ("EXIT CODE: {}, {}".format(exit_code, message))
      end_time = time.time()
      await monitoring_log_output(message, exit_code, reader, writer)
def search_devices(ser, sleep_time, status): # Searches for all sender cards connected to each USB port (/dev/ttyUSBX) on the system
   logger = logging.getLogger(LOGGER_NAME)
   ports = serial.tools.list_ports.comports()
   logger.info("Found {} serial ports".format(len(ports)))
   device_found = 0
   valid_ports = []
   for port, desc, hwid in sorted(ports):
      logger.info("Searching sender card on port: " + port)
      ser.port = port
      try: 
         ser.open()
      except Exception as e:
         logger.error(str(e))
      if ser.isOpen():
         logger.info("{} opened".format(port)) # remove at production
         try:
            ser.flushInput() # flush input buffer, discarding all its contents
            ser.flushOutput() # flush output buffer, aborting current output and discard all that is in buffer
            ser.write (connection) # send CONNECTION command to check whether any devices are connected
            logger.debug("Sending command: " + ' '.join('{:02X}'.format(a) for a in connection))
            time.sleep (sleep_time) # allow some time for the device to respond        
            if ser.inWaiting()>0: # there should be something at the serial input
               response = ser.read(size=ser.inWaiting()) # read all the data available
               rx_data = list(response)
               logger.debug("Received data:"+' '.join('{:02X}'.format(a) for a in rx_data))
               if check_response(rx_data):                        
                  if (rx_data[18]!=0 or rx_data [19]!=0): # if ACKNOWLEDGE data is not equal to zero then a device is connected
                        # **********************************************************
                        status[port] = {} 
                        #status[port]["lastUpdated"] = last_updated
                        status[port]["connectedControllers"] = device_found
                        status[port]["targetPort"] = port
                        status[port]["controllerDescription"] = desc
                        status[port]["controllerHardware"] = hwid
                        # **********************************************************
                        device_found =  device_found + 1
                        connected_port = port
                        valid_ports.append(port)
                        logger.info("Device found on port: {} | {} | {}".format(port, desc, hwid))                       
                  else:
                        logger.info("Device not connected")
         except Exception as e1:
            logger.error("Error communicating with device: " + str(e1))
         ser.close()
         logger.info("{} closed".format(port)) # remove at production?
   logger.info("Found {} device(s)".format(device_found))
   return device_found, valid_ports
def check_response(received_data):
   logger = logging.getLogger(LOGGER_NAME)
   try:
      if (received_data[2]==0):   
         return True
      elif (received_data[2]==1):
         logger.error('Command failed due to time out (time out on trying to access devices connected to a sending card)')
      elif (received_data[2]==2):
         logger.error('Command failed due to check error on request data package')
      elif (received_data[2]==3):
         logger.error('Command failed due to check error on acknowledge data package')
      elif (received_data[2]==4):
         logger.error('Command failed due to invalid command')
      else:
         logger.error('Command failed due to unkown error')
      return False
   except Exception as e:
      logger.error('Command failed due to error: {}'.format(e))
      return False
async def monitoring_log_output(message, exit_status, reader, writer):
   global data
   global logger
   #output to log monitor_log_file.log
   alarm = GOOD
   if WARNING in exit_status:
      alarm = WARNING
   elif CRITICAL in exit_status:
      alarm = CRITICAL
   else:
      alarm = UNKNOWN    
   try:
      session_handler(writer,reader)
      logger.info("check completed successfully")
      with open("monitor_log.log", "w") as log:
         log.write(f"{message}={alarm}")
   except Exception as e:
      logger.error(f"Error sending completion message: {e}")
   exit()
async def session_handler(writer, reader):
   writer.write(b"Done")
   await writer.drain()
   await reader.read(1024)
   writer.close()
   await writer.wait_closed() 