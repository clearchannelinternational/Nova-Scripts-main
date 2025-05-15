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
class base:
   def __init__(self):
      self.sleep_time = .5
      self.flash_wait_time = 0
      self.status = {}
      self.last_updated = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
      self.data = {}
      self.logger = None
      self.config = {}
      self.device_found = 0
      self.valid_ports = 0
      self.ser = None
      self.config_panel = {}
      self.baudrates = []
   if platform == "linux":
      dir = "/data/opt/LEDMonitoring"
      hostname = os.getenv('HOSTNAME', 'defaultValue')
   else:
      dir = r"C:\LEDMonitoring"
      hostname = os.getenv('COMPUTERNAME', 'defaultValue')
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
   async def communicate_with_server(self, callback, check_name):

      self.logger = methods.get_logger(check_name,self.LOG_FILE,self.FORMATTER,self.LOGGER_SCHEDULE,self.LOGGER_INTERVAL,self.LOGGER_BACKUPS) # Set up the logging  
      self.logger.info("ESTABLISHING CONNECTION WITH LOCAL SERVER QUEUE")
      reader, writer = await asyncio.open_connection("127.0.0.1",8888)
      if not reader and not writer:
         logger.error("COULD NOT ESTABLISH CONNECTION WITH 127.0.0.1 ON PORT 8888")
      writer.write(f"{check_name}".encode())
      await writer.drain()
      self.logger.info("AWAITING PERMISSION TO USE COM PORTS FROM LOCAL SERVER")
      self.data = await reader.read(1024)
      if not self.data.decode().strip() == "START":
         self.logger.error("Could not make connection with localserver to access com port")
         self.session_handler(writer,reader)
         exit()
      self.logger.info(f"PERMISSION TO USE COM PORT GRANTED STARTING {check_name} SCRIPT")
      await callback(reader, writer) #callback is the method passed to run after permission is granted   
   async def initialize_program(self, reader, writer):
      module_status_info = {}
      self.logger = methods.get_logger(self.LOGGER_NAME,self.LOG_FILE,self.FORMATTER,self.LOGGER_SCHEDULE,self.LOGGER_INTERVAL,self.LOGGER_BACKUPS) # Set up the logging
      self.logger.info("*********************************************************************************************************************************************")
      self.logger.info("5Eyes - Starting Display Status Checks")
      self.config = loadConfig(self.LOGGER_NAME) # Load the configuration information
      self.baudrates = self.config["baudrate"]
      self.logger.info("Version: {}, Baudrate: {}, Sleep Time: {}, Flash Timeout: {}".format(self.config["version"],self.baudrates,self.config["sleepTime"],self.config["flashWaitTime"]))
      self.last_updated = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
      sleep_time = float(self.config["sleepTime"])
      self.flash_wait_time = float(self.config["flashWaitTime"])
      self.data = read_data(self.STATUS_FILE,self.LOGGER_NAME)
      self.status = {} # Initialise variable to store status data\
      self.modules_ok = True # assume all modules are ok to start off
      self.number_of_modules = self.config["modules"]
      
      if self.hostname in self.config.keys():
         self.config_panel = self.config[self.hostname]
      else:
         self.config_panel = self.config['default']
      
      for baudrate in self.baudrates:
         self.ser = methods.setupSerialPort(baudrate,self.LOGGER_NAME) # Initialise serial port
         self.device_found, self.valid_ports = self.search_devices()

         #Validate device found on player
      if not self.valid_ports:
         message = "NO DEVICE - make sure a valid controller is connected, that the correct baudrate is defined in config.json and ensure the NOVA LCT is not running on the host system \nThis can also mean that you don't run the tool as administrator"
         exit_code = self.CRITICAL
         self.logger.info ("EXIT CODE: {}, {}".format(exit_code, message))
         await self.monitoring_log_output(message, exit_code, reader, writer)
   def search_devices(self): # Searches for all sender cards connected to each USB port (/dev/ttyUSBX) on the system
      self.logger = logging.getLogger(self.LOGGER_NAME)
      ports = serial.tools.list_ports.comports()
      self.logger.info("Found {} serial ports".format(len(ports)))
      device_found = 0
      valid_ports = []
      for port, desc, hwid in sorted(ports):
         self.logger.info("Searching sender card on port: " + port)
         self.ser.port = port
         try: 
            self.ser.open()
         except Exception as e:
            self.logger.error(str(e))
         if self.ser.isOpen():
            self.logger.info("{} opened".format(port)) # remove at production
            try:
               self.ser.flushInput() # flush input buffer, discarding all its contents
               self.ser.flushOutput() # flush output buffer, aborting current output and discard all that is in buffer
               self.ser.write (connection) # send CONNECTION command to check whether any devices are connected
               self.logger.debug("Sending command: " + ' '.join('{:02X}'.format(a) for a in connection))
               time.sleep (self.sleep_time) # allow some time for the device to respond        
               if self.ser.inWaiting()>0: # there should be something at the serial input
                  response = self.ser.read(size=self.ser.inWaiting()) # read all the data available
                  rx_data = list(response)
                  self.logger.debug("Received data:"+' '.join('{:02X}'.format(a) for a in rx_data))
                  if self.check_response(rx_data):                        
                     if (rx_data[18]!=0 or rx_data [19]!=0): # if ACKNOWLEDGE data is not equal to zero then a device is connected
                           # **********************************************************
                           self.status[port] = {} 
                           #status[port]["lastUpdated"] = last_updated
                           self.status[port]["connectedControllers"] = device_found
                           self.status[port]["targetPort"] = port
                           self.status[port]["controllerDescription"] = desc
                           self.status[port]["controllerHardware"] = hwid
                           # **********************************************************
                           device_found =  device_found + 1
                           self.connected_port = port
                           valid_ports.append(port)
                           self.logger.info("Device found on port: {} | {} | {}".format(port, desc, hwid))                       
                     else:
                           self.logger.info("Device not connected")
            except Exception as e1:
               self.logger.error("Error communicating with device: " + str(e1))
            self.ser.close()
            self.logger.info("{} closed".format(port)) # remove at production?
      self.logger.info("Found {} device(s)".format(device_found))
      return device_found, valid_ports
   def check_response(self, received_data):
      self.logger = logging.getLogger(self.LOGGER_NAME)
      try:
         if (received_data[2]==0):   
            return True
         elif (received_data[2]==1):
            self.logger.error('Command failed due to time out (time out on trying to access devices connected to a sending card)')
         elif (received_data[2]==2):
            self.logger.error('Command failed due to check error on request data package')
         elif (received_data[2]==3):
            self.logger.error('Command failed due to check error on acknowledge data package')
         elif (received_data[2]==4):
            self.logger.error('Command failed due to invalid command')
         else:
           self.logger.error('Command failed due to unkown error')
         return False
      except Exception as e:
         self.logger.error('Command failed due to error: {}'.format(e))
         return False
   async def monitoring_log_output(self,message, monitor_message, exit_status, reader, writer):
      #output to log monitor_log_file.log
      alarm = self.UNKNOWN
      if self.WARNING == exit_status:
         alarm = self.WARNING
      elif self.CRITICAL == exit_status:
         alarm = self.CRITICAL
      else:
         alarm = self.GOOD    
      try:
         await self.session_handler(writer,reader)
         self.logger.info("check completed successfully")         
      except Exception as e:
         self.logger.error(f"Error sending completion message: {e}")
      with open("monitor_log.log", "w") as log:
            log.write(f"{monitor_message}={alarm}")
      exit()
   async def session_handler(self, writer, reader):
      writer.write(b"Done")
      await writer.drain()
      await reader.read(1024)
      writer.close()
      await writer.wait_closed()