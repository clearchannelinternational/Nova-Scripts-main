import serial
import time
import serial.tools.list_ports
import logging
from logging.handlers import TimedRotatingFileHandler
import methods
from methods import read_data, write_data, loadConfig
from module_functions import *

# ------------------------------------------------------------------------------------------------------------
# DEFINITIONS AND INITIALISATIONS

# LOGGER
FORMATTER = logging.Formatter('%(asctime)s %(name)s %(levelname)-8s %(message)s', datefmt='%d/%m/%Y %H:%M:%S')
LOG_FILE = "debug.log"
LOGGER_NAME = 'display_status'
LOGGER_SCHEDULE = 'midnight'
LOGGER_BACKUPS = 7
LOGGER_INTERVAL = 1

# EXIT CODES
GOOD = 0
WARNING = 1
CRITICAL = 2
UNKNOWN = 3

# COMMANDS
COMMANDS = {
"connection" : list (b"\x55\xAA\x00\xAA\xFE\x00\x00\x00\x00\x00\x00\x00\x02\x00\x00\x00\x02\x00\x01\x57"), # Reconnect Sending Card/Receiving Card
"sender_model" : list (b"\x55\xAA\x00\x32\xFE\x00\x00\x00\x00\x00\x00\x00\x02\x00\x00\x00\x02\x00\x87\x56"), #sender card model number
"sender_firmware" : list (b"\x55\xAA\x00\x15\xFE\x00\x00\x00\x00\x00\x00\x00\x04\x00\x10\x04\x04\x00\x84\x56"), #sender card FW version
"check_receiver_fw" : list (b"\x55\xAA\x00\x32\xFE\x00\x01\x00\x00\x00\x00\x00\x04\x00\x00\x08\x04\x00\x96\x56"), #A valid Firmware version is a value other than 00 00 00 00
"check_receiver_model" : list (b"\x55\xAA\x00\x15\xFE\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x6B\x56"), # A valid Model ID is a value other than 00.
"check_monitoring" : list (b"\x55\xAA\x00\x32\xFE\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x0A\x00\x01\x91\x56"), # Acquire monitoring data or first receiver
"input_source_status" : list (b"\x55\xAA\x00\x32\xFE\x00\x00\x00\x00\x00\x00\x00\x22\x00\x00\x02\x01\x00\xAA\x56"), #check is input source selection is manual or automatic
"current_input_source" : list (b"\x55\xAA\x00\x32\xFE\x00\x00\x00\x00\x00\x00\x00\x23\x00\x00\x02\x01\x00\xAB\x56"), #verify/select the current input source (only on models different from MCTRL300),
"input_source_port" : list (b"\x55\xAA\x00\x32\xFE\x00\x00\x00\x00\x00\x00\x00\x4D\x00\x00\x02\x01\x00\xD5\x56"), # NEEDS CHECKING 
"check_DVI_signal" : list (b"\x55\xAA\x00\x16\xFE\x00\x00\x00\x00\x00\x00\x00\x17\x00\x00\x02\x01\x00\x83\x56 "), #DVI signal checking
"check_auto_bright" : list (b"\x55\xAA\x00\x5B\xFE\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x0A\x01\x00\xB9\x56"), #check brightness mode, whether ALS is ENABLED or DISABLED
"check_ALS_direct" : list (b"\x55\xAA\x00\x5B\xFE\x00\x00\x00\x00\x00\x00\x00\x0F\x00\x00\x02\x02\x00\xC1\x56"), # ALS checking
"check_ALS_function" : list (b"\x55\xAA\x00\x15\xFE\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00\x06\x05\x00\x75\x56"),
"get_brightness" : list (b"\x55\xAA\x00\x14\xFE\x00\x01\x00\x00\x00\x00\x00\x01\x00\x00\x02\x05\x00\x70\x56"), # get receiver brightness
"display_brightness" : list (b"\x55\xAA\x00\x15\xFE\x00\x01\x00\x00\x00\x00\x00\x01\x00\x00\x02\x05\x00\x70\x56"), # get receiver brightness
"kill_mode" : list (b"\x55\xAA\x00\x80\xFE\x00\x01\x00\x00\x00\x00\x00\x00\x01\x00\x02\x01\x00\xD8\x57"), #Turn display OFF (:KILL), or ON (:NORMAL),
"lock_mode" : list (b"\x55\xAA\x00\x80\xFE\x00\x01\x00\x00\x00\x00\x00\x02\x01\x00\x02\x01\x00\xD8\x57"),
"check_cabinet_width" : list (b"\x55\xAA\x00\x32\xFE\x00\x00\x00\x00\x00\x00\x00\x06\x00\x10\x02\x02\x00\x9F\x56"), #read cabinet width
"check_cabinet_height" : list (b"\x55\xAA\x00\x32\xFE\x00\x00\x00\x00\x00\x00\x00\x08\x00\x10\x02\x02\x00\xA1\x56"), #read cabinet height
"gamma_value" : list (b"\x55\xAA\x00\x15\xFE\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x02\x01\x00\x6C\x56"),
"auto_brightness_settings" : list (b"\x55\xAA\x00\x5B\xFE\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x0A\x2F\x00\xB9\x56"),
"start_check_module_flash" : list (b"\x55\xAA\x00\xF2\xFE\x00\x01\x00\x00\x00\x01\x00\x74\x00\x00\x01\x01\x00\x04\xC1\x57"),
"read_back_module_flash" : list (b"\x55\xAA\x00\x03\xFE\x00\x01\x00\x00\x00\x00\x00\x10\x30\x00\x03\x10\x00\xAA\x56"),
"ribbon_cable" : list (b"\x55\xAA\x00\x32\xFE\x00\x01\x00\x00\x00\x00\x00\x42\x00\x00\x0A\x10\x00\xE2\x56"),
"edid_register" : list (b"\x55\xAA\x00\x15\xFE\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08\x7F\x00\xE2\x56"),
"check_redundancy" : list (b"\x55\xAA\x00\x15\xFE\x00\x00\x00\x00\x00\x00\x00\x00\x1E\x00\x02\x01\x00\xE2\x56"),
"check_function_card" : list (b"\x55\xAA\x00\x32\xFE\x00\x02\x00\x00\x00\x00\x00\x02\x00\x00\x00\x02\x00\x8B\x56"),
"function_card_refresh_register" : list (b"\x55\xAA\x00\x15\xFE\x00\x02\x00\x00\x00\x01\x00\x00\x00\x00\x06\x0B\x00\x00\x00\x00\x00\x55\xAA\x01\x02\x80\xFF\x81\x7E\x59"),
#################################################################################################
"check_module_status" : list (b"\x55\xAA\x00\xC4\xFE\x00\x01\x00\x00\x00\x00\x00\x0A\x00\x00\x0A\x18\x00\x7E\x59"),
#################################################################################################
#Alvin's check LED module code
#################################################################################################
"get_status" : list (b"\x55\xAA\x00\xC4\xFE\x00\x01\x00\x00\x00\x00\x00\x0A\x00\x00\x0A\x18\x00\x7E\x59"),
#################################################################################################
}
# ------------------------------------------------------------------------------------------------------------

# ------------------------------------------------------------------------------------------------------------
# FUNCTION DEFINITIONS
#################################################################################################
def get_module_status_one(port,  modules_ok):
#-----------------------------------------------------------------
   global no_of_receiver_cards
   global number_of_modules
   logger = logging.getLogger(LOGGER_NAME)
   logger.info("Getting module status")
   COMMANDS["check_module_status"][8] = no_of_receiver_cards
   data_groups = 4
   data_length = number_of_modules * (22+2*data_groups)
   print (data_length)
   first_byte = data_length & 0xFF00
   second_byte = data_length & 0x00FF
   print (first_byte, second_byte)
   COMMANDS["check_module_status"][16] = second_byte
   COMMANDS["check_module_status"][17] = first_byte
   element_length = 22 + (data_groups*2)
   print (element_length)
   # Here we must adjust length of data to be read (L) for NUMBER OF MODULES (N) and for DATA GROUPS PER MODULE (DG) according to the formula:
   # L = N * (22+2*DG)
   # Assumption for now is that N=4 (this value may be stored in config.json) and DG=1. Therefore:
   # L = 4 * (22+2*1) = 4 * (24) = 96 = 0x60 --> check_module_status [16] = 96
   check_module_status_send = methods.checksum(COMMANDS["check_module_status"])
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in check_module_status_send))
   ser.write(check_module_status_send)
   time.sleep(sleep_time)
   modules_ok = True
   # ------------------------------------------------------------------------------------------------
   # Read length of payload data received - payload will contain info for all N modules.
   # First byte (X0)represents LED module status (xFF=NORMAL; 0x00=PROBLEM)
   # (X1) to (X21) represents other data (such as power supply voltage, temperature and runtime of module?)
   # (X22) and (X23) represent cable detection --> These should both be 0 - any other value means an error
   # 
   # ------------------------------------------------------------------------------------------------
   if ser.inWaiting()>0:
         response = ser.read(size=ser.inWaiting())
         rx_data = list (response)
         logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
         #number_of_modules = int(rx_data[16]/4)
         #logger.info ("Total amount of modules: {}".format(number_of_modules))
         status[port]["receiverCard"][no_of_receiver_cards]["module"]={}
         if check_response(rx_data):
            # Read X0-X23 bytes for each module expected
            # First, read the X0 byte for LED module status
            # Next, check flat cable data in bytes X22 and X23.
            # The Data Groups consist of 2 bytes (16 bits). Each bit is a Data Flag
            for j in range (int(number_of_modules)):
               status[port]["receiverCard"][no_of_receiver_cards]["module"][j]={}
               element = rx_data[18+j*element_length:(18+j*element_length)+element_length]
               #print("MODULE STATUS: {:02X}",hex(element))
               logger.debug("MODULE STATUS: "+' '.join('{:02X}'.format(a) for a in element))
               if (element[0]==0xFF):
                  module_sts= "OK"
                  modules_ok = modules_ok and True
               else:
                  if (element[0]==0x00):
                     module_sts = "Error or no module available"
                     modules_ok = modules_ok and False
                  else:
                     module_sts = "Unknown module state"
                     modules_ok = modules_ok and True
               if ((element[22] & 0xF) != 0) | ((element[24] & 0xF) != 0) | ((element[26] & 0xF) != 0)| ((element[28] & 0xF) != 0):
                  block_fault = "FAULT"
               else:
                  block_fault = "OK"
               logger.info ("Module {module_index}: STATUS:{write_result} (0x{write_hex:02X})   BLOCK FAULTS:{block}".format(module_index=j+1,write_result=module_sts,write_hex=element[0],block=block_fault))#.format(j+1).format(module_write).format(element[0]).format(module_read).format(element[1]))
               status[port]["receiverCard"][no_of_receiver_cards]["module"][j]=module_sts
         else:
            modules_ok = modules_ok and False
            status[port]["receiverCard"][no_of_receiver_cards]["module"]='N/A'
   else:
         logger.warning ("No data available at the input buffer")    
         number_of_modules = 0
         modules_ok = modules_ok and False
         module_status="N/A"    
         status[port]["receiverCard"][no_of_receiver_cards]["module"]="N/A"
   return (number_of_modules,modules_ok)
#################################################################################################

def search_devices(): # Searches for all sender cards connected to each USB port (/dev/ttyUSBX) on the system
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
                  ser.write (COMMANDS["connection"]) # send CONNECTION command to check whether any devices are connected
                  logger.debug("Sending command: " + ' '.join('{:02X}'.format(a) for a in COMMANDS["connection"]))
                  time.sleep (sleep_time) # allow some time for the device to respond        
                  if ser.inWaiting()>0: # there should be something at the serial input
                     response = ser.read(size=ser.inWaiting()) # read all the data available
                     rx_data = list(response)
                     logger.debug("Received data:"+' '.join('{:02X}'.format(a) for a in rx_data))
                     if check_response(rx_data):                        
                        if (rx_data[18]!=0 or rx_data [19]!=0): # if ACKNOWLEDGE data is not equal to zero then a device is connected
                              # **********************************************************
                              status[port] = {} 
                              status[port]["lastUpdated"] = last_updated
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
      else:
         if (received_data[2]==1):
            logger.error('Command failed due to time out (time out on trying to access devices connected to a sending card)')
         else:
            if (received_data[2]==2):
               logger.error('Command failed due to check error on request data package')
            else:
                  if (received_data[2]==3):
                     logger.error('Command failed due to check error on acknowledge data package')
                  else:
                        if (received_data[2]==4):
                           logger.error('Command failed due to invalid command')
                        else:
                           logger.error('Command failed due to unkown error')
         return False
   except Exception as e:
      logger.error('Command failed due to error: {}'.format(e))
      return False

def get_sender_card_model(port):
# ---------------------------------------------------------------------------------------
# DETERMINE SENDER CARD MODEL
# Check which sender card hardware model is connected.
# NOTE - Different sender cards use different baud rates; may require a method for changing this
# Device: Sending Card 
# Base Address: 0x0000_0000H 
# Data Length: 2H
# -----------------------------
   logger = logging.getLogger(LOGGER_NAME)
   logger.info("Getting sender card model")
   sender_model_send = methods.checksum(COMMANDS["sender_model"])
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in sender_model_send))
   ser.write (sender_model_send)
   time.sleep (sleep_time)
   if ser.inWaiting()>0:
      response = ser.read(size=ser.inWaiting())
      rx_data = list(response)
      logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
      if check_response(rx_data):
         if (rx_data[18]==1 and rx_data[19]==1):
            model="MCTRL500"
         else:
            if (rx_data[18]==1 and rx_data[19]==0):
                  model="MSD300/MCTRL300"
            else:
                  if (rx_data[18]==1 and rx_data[19]==0x11):
                     model="MSD600/MCTRL600/MCTRL610/MCTRL660"
                  else:
                     model="Unknown"
      else:
          model="N/A"
   else:
      logger.warning("No data available at the input buffer")
      model="N/A"
   status[port]["controllerModel"] = model
   logger.info("Sender card model: " + model)
   return (model)

def get_sender_card_firmware_version(port):
# ---------------------------------------------------------------------------------------
# FIRMWARE VERSION
# Request firmware version of the sender card 
# Device: Sending Card
# Base Address: 0x0400_0000H 
# Data Length: 4H
# -----------------------------
   logger = logging.getLogger(LOGGER_NAME)
   logger.info("Getting device firmware version")
   sender_firmware_send = methods.checksum(COMMANDS["sender_firmware"])
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in sender_firmware_send))
   ser.write (sender_firmware_send)
   time.sleep (sleep_time)
   if ser.inWaiting()>0:
      response = ser.read(size=ser.inWaiting())
      rx_data = list(response)
      logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
      if check_response(rx_data):
         firmware=str(rx_data[18])+"."+str(rx_data[19])+"."+str(rx_data[20])+"."+str(rx_data[21])
      else:
          firmware="N/A"
   else:
      logger.warning("No data available at the input buffer")
      firmware="N/A"
   status[port]["controllerFirmware"] = firmware
   logger.info("Sender card firmware version: "+ firmware)

   return(firmware)

def get_input_source_mode(port):
#---------------------------------------------------------------------------------------
# CHECK INFORMATION REGARDING VIDEO (FROM SENDER CARD)
# Applicable to sender cards with multiple video inputs such as MSD600/MCTRL600/MCTRL610/MCTRL660
# ---------------------------------------------------------------------------------------
   logger = logging.getLogger(LOGGER_NAME)
   logger.info("Getting input source mode")
   input_source_status_send = methods.checksum(COMMANDS["input_source_status"])
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in input_source_status_send))
   ser.write (input_source_status_send)
   time.sleep (sleep_time)
   if ser.inWaiting()>0:
      response = ser.read(size=ser.inWaiting())
      rx_data = list(response)
      logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
      if check_response(rx_data):
         if (rx_data[18]!=0x5A):
            video_mode="AUTOMATIC"
         else:
            video_mode="MANUAL"
      else:
           video_mode="N/A"
   else:
      logger.warning("No data available at the input buffer")
      video_mode="N/A"
   status[port]["inputSourceMode"] = video_mode
   logger.info("Input source mode: "+ video_mode)

   return(video_mode)

def get_input_source_selected(port):
# ---------------------------------------------------------------------------------------
# INPUT SOURCE SELECTED
# Applicable to sender cards with multiple video inputs such as MSD600/MCTRL600/MCTRL610/MCTRL660
# ---------------------------------------------------------------------------------------
   logger = logging.getLogger(LOGGER_NAME)
   logger.info("Getting input source port selected")
   current_input_source_send = methods.checksum(COMMANDS["current_input_source"])
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in current_input_source_send))
   ser.write (current_input_source_send)
   time.sleep (sleep_time)
   if ser.inWaiting()>0:
      response = ser.read(size=ser.inWaiting())
      rx_data = list(response)
      logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
      if check_response(rx_data):
         if (rx_data[18]==0x58):
            video_port="DVI"
         else:
            if (rx_data[18]==0x61):
                     video_port="Dual DVI"
            else:
                     if(rx_data[18]==0x05):
                        video_port="HDMI"
                     else:
                        if(rx_data[18]==0x01):
                              video_port="3G-SDI"
                        else:
                              if(rx_data[18]==0x5F):
                                 video_port="DisplayPort"
                              else:
                                 if(rx_data[18]==0x5A):
                                    video_port="HDMI 1.4"
                                 else:
                                          video_port="N/A or not selected"
      else:
         video_port="N/A"
   else:
         logger.warning("No data available at the input buffer")
         video_port="N/A"
   status[port]["inputSourcePort"] = video_port
   logger.info("Input source port: "+ video_port)

   return(video_port)

def get_input_source_status(port):
#---------------------------------------------------------------------------------------
# INPUT SOURCE STATUS
# Applicable to sender cards with multiple video inputs such as MSD600/MCTRL600/MCTRL610/MCTRL660
# ---------------------------------------------------------------------------------------
  #**** TO CHECK ******
   logger = logging.getLogger(LOGGER_NAME)
   logger.info("Getting input source status")
   input_source_port_send = methods.checksum(COMMANDS["input_source_port"])
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in input_source_port_send))
   ser.write (input_source_port_send)
   time.sleep (sleep_time)
   if ser.inWaiting()>0:
      response = ser.read(size=ser.inWaiting())
      rx_data = list(response)
      logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
      if check_response(rx_data):
         input_status = rx_data[18]
         if (input_status == 0xFF):
            source_status="N/A (x{:02X})".format(input_status)
         else:
            if (input_status & 1):
                     source_status="3G-SDI"
            else:                   
               if (input_status & 2):
                        source_status="HDMI"
               else:
                     if (input_status &4 ):
                           source_status="DVI-1"
                     else:
                        if (input_status & 8):
                                 source_status="DVI-2"
                        else:
                           if (input_status & 16):
                                 source_status="DVI-3"
                           else:
                                 if (input_status & 32):
                                    source_status="DVI-4"
                                 else:
                                    if (input_status & 64):
                                       source_status="DisplayPort"
                                    else:
                                             source_status="N/A (x{:02X})".format(input_status)
      else:
         source_status="N/A"
   else:   
         logger.warning("No data available at the input buffer")
         source_status="N/A"
   status[port]["inputSourceStatus"] = source_status
   logger.info("Valid input on: "+ source_status)

   return(source_status)

def get_DVI_signal_status(port):
# ---------------------------------------------------------------------------------------
# DVI SIGNAL CHECK
# Device: Sending Card
# Base Address: 02000000 H 
# Data Length: 1H
# Applicable to all sender cards
# ---------------------------------------------------------------------------------------
   logger = logging.getLogger(LOGGER_NAME)
   logger.info("Getting DVI signal")
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in COMMANDS["check_DVI_signal"]))
   ser.write (COMMANDS["check_DVI_signal"])
   time.sleep (sleep_time)
   if ser.inWaiting()>0:
      response = ser.read(size=ser.inWaiting())
      rx_data = list(response)
      logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
      if check_response(rx_data):
         if (rx_data[18]==0x00):
            DVI_valid = "Not valid"
         else:
            if (rx_data[18]==0x01):
                     DVI_valid = "Valid"
            else:
                     DVI_valid = "Unknown"
      else:
         DVI_valid = "N/A"
   else:
         logger.warning("No data available at the input buffer")
         DVI_valid = "N/A"
   status[port]["DVISignal"] = DVI_valid
   logger.info("DVI signal: "+ DVI_valid)
   return (DVI_valid)

def get_ALS_mode_status(port):
# ---------------------------------------------------------------------------------------
# ALS MODE
# Device: Sending Card
# Base Address: 0x0A00_0000H 
# Data Length: 1H
# ---------------------------------------------------------------------------------------
   logger = logging.getLogger(LOGGER_NAME)
   logger.info("Getting automatic brightness mode")
   check_auto_bright_send = methods.checksum(COMMANDS["check_auto_bright"])
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in check_auto_bright_send))
   ser.write (check_auto_bright_send)
   time.sleep (sleep_time)
   if ser.inWaiting()>0:
      response = ser.read(size=ser.inWaiting())
      rx_data = list(response)
      logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
      if check_response(rx_data):
         if (rx_data[18]==0x7D):
            ALS_mode="Enabled"
         else:
            if (rx_data[18]==0xFF):
                  ALS_mode="Disabled"
            else:
                  ALS_mode="Unknown (0x{:02X})".format(rx_data[18])
      else:
         ALS_mode="N/A" 
   else:
         logger.warning("No data available at the input buffer")
         ALS_mode="N/A"
   status[port]["ALSMode"] = ALS_mode
   logger.info("Automatic Brightness Mode: "+ ALS_mode)
   return(ALS_mode)

def get_ALS_mode_settings(port):
# ---------------------------------------------------------------------------------------
# AUTOMATIC BRIGHTNESS SETTINGS
# ---------------------------------------------------------------------------------------
   logger = logging.getLogger(LOGGER_NAME)
   logger.info("Getting Automatic Brightness Settings...[TO CHECK]")
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in COMMANDS["auto_brightness_settings"]))
   auto_brightness_settings_send = methods.checksum(COMMANDS["auto_brightness_settings"])
   ser.write (auto_brightness_settings_send)
   time.sleep (sleep_time)
   if ser.inWaiting()>0:
      response = ser.read(size=ser.inWaiting())
      rx_data = list(response)
      logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
      if check_response(rx_data):
         logger.info ("Number of light sensors: {}".format(rx_data[18]))
         status[port]["ALSQuantity"] = rx_data[18]

         max = (rx_data[23]<<8) + rx_data[22]
         logger.info  ("Max Lux: {}".format(max))
         status[port]["maxLux"] = max

         min = (rx_data[25]<<8)+ rx_data[24]
         logger.info  ("Min Lux: {}".format(min))
         status[port]["minLux"] = min

         max_brightness = rx_data[26]
         max_brightness_pc=int(100*max_brightness/255)
         logger.info("Max Brightness (0-255): {}".format(max_brightness))
         logger.info  ("Max Brightness: {}% ".format(max_brightness_pc))
         status[port]['maxBright'] = max_brightness
         status[port]["maxBrightPC"] = max_brightness_pc

         min_brightness = rx_data[27]
         min_brightness_pc= int(100*min_brightness/255)
         logger.info("Min Brightness (0-255): {}".format(min_brightness))
         logger.info  ("Min Brightness: {}% ".format(min_brightness_pc))
         status[port]['minBright'] = min_brightness
         status[port]["minBrightPC"] = min_brightness_pc

         logger.info  ("Number of steps: {}".format(rx_data[28]))
         status[port]["numSteps"] = rx_data[28]
         logger.info  ("Light Sensor Position: {}".format(rx_data[49]))
         status[port]["ALSPosition"] = rx_data[49]
         logger.info  ("Port Address Position: {}".format(rx_data[50]))
         status[port]["PortPosition"] = rx_data[50]
         logger.info  ("Function Card Position: {} {}".format(hex(rx_data[42]),hex(rx_data[41])))

         status[port]["functionCardPosition (LOW)"] = hex(rx_data[41])
         status[port]["functionCardPosition (HIGH)"] = hex(rx_data[21])
         logger.info  ("Address of sensor on Function Card: {}".format(rx_data[43]))
         status[port]["functionCardAddress"] = rx_data[43]
      else:
         status[port]["ALSQuantity"] = 'N/A'
         status[port]["maxLux"] = 'N/A'
         status[port]["minLux"] = 'N/A'
         status[port]['maxBright'] = 'N/A'
         status[port]["maxBrightPC"] = 'N/A'
         status[port]['minBright'] = 'N/A'
         status[port]["minBrightPC"] = 'N/A'
         status[port]["minBrightNits"] = 'N/A'
         status[port]["numSteps"] = 'N/A'
         status[port]["ALSPosition"] = 'N/A'
         status[port]["PortPosition"] = 'N/A'
         status[port]["functionCardPosition"] = 'N/A'
         status[port]["functionCardAddress"] = 'N/A'
   else:
      logger.warning("No data available at the input buffer")

def get_ambient_light_level_direct(port):
# ---------------------------------------------------------------------------------------
# AMBIENT LIGHT LEVEL
# Device: Sending Card
# Base Address: 0x0200_0000H
# Data Length: 2H
# ---------------------------------------------------------------------------------------
   logger = logging.getLogger(LOGGER_NAME)
   logger.info("Getting ambient light level directly from controller")
   check_ALS_send = methods.checksum(COMMANDS["check_ALS_direct"])
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in check_ALS_send))
   ser.write (check_ALS_send)
   time.sleep (sleep_time)
   if ser.inWaiting()>0:
      response = ser.read(size=ser.inWaiting())
      rx_data = list(response)
      logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
      if check_response(rx_data):
         if (rx_data[19]&0x80==0x80):
            # TODO - INCLUDE DATA READ VALID
            ambient_light_lux=rx_data[18]*(0xFFFF/0xFF)
         else:
            print ("Returned data is not valid")
            # TODO - INCLUDE DATA READ INVALID
            ambient_light_lux="Data invalid (0x{:02X})".format(int(rx_data[18]*(0xFFFF/0xFF)))
      else:
         ambient_light_lux="N/A"
   else:
         logger.warning("No data available at the input buffer")
         ambient_light_lux="N/A"
   status[port]["ambientLightLevel"] = ambient_light_lux
   logger.info("Ambient Light Level (lux): {} ".format(ambient_light_lux))  

   return(ambient_light_lux)  

def get_ambient_light_level_via_function_card(port):
# ---------------------------------------------------------------------------------------
# AMBIENT LIGHT LEVEL
# Device: Sending Card
# Base Address: 0x0200_0000H
# Data Length: 2H
# ---------------------------------------------------------------------------------------
   logger = logging.getLogger(LOGGER_NAME)
   logger.info("Refreshing function card register")
   refresh_function_send = methods.checksum(COMMANDS["function_card_refresh_register"])
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in refresh_function_send))
   ser.write (refresh_function_send)
   time.sleep (sleep_time)
   if ser.inWaiting()>0:
      response = ser.read(size=ser.inWaiting())
      rx_data = list(response)
      logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
   else:
         logger.warning("No data available at the input buffer")
   logger.info("Getting ambient light level from function card")
   check_ALS_send = methods.checksum(COMMANDS["check_ALS_function"])
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in check_ALS_send))
   ser.write (check_ALS_send)
   time.sleep (sleep_time)
   if ser.inWaiting()>0:
      response = ser.read(size=ser.inWaiting())
      rx_data = list(response)
      logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
      if check_response(rx_data):
         if (rx_data[20]&0x80==0x80):
            ambient_light_lux=rx_data[21]*(0xFFFF/0xFF)
         else:
            ambient_light_lux="Data invalid (0x{:02X})".format(int(rx_data[18]*(0xFFFF/0xFF)))
      else:
         ambient_light_lux="N/A"
   else:
         logger.warning("No data available at the input buffer")
         ambient_light_lux="N/A"
   status[port]["ambientLightLevel"] = ambient_light_lux
   logger.info("Ambient Light Level (lux): {} ".format(ambient_light_lux))

   return(ambient_light_lux)    

def get_brightness_levels(port):
# ---------------------------------------------------------------------------------------
# SCREEN BRIGHTNESS SETTINGS
# This needs to be on a per receiver card basis or global?
# ---------------------------------------------------------------------------------------
   logger = logging.getLogger(LOGGER_NAME)
   logger.info("Getting current screen brightness...[TO CHECK]")
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in COMMANDS["get_brightness"]))
   ser.write (COMMANDS["get_brightness"])
   time.sleep (sleep_time)
   if ser.inWaiting()>0:
      response = ser.read(size=ser.inWaiting())
      rx_data = list(response)
      logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
      if check_response(rx_data):
         brightness = rx_data[18]
         brightness_pc = round(100*brightness/255)
         brightness_nits = round(brightness_pc*int(COMMANDS["setup_data"]['nominalBrightness'])/100)
         logger.info("Brightness Level: "+ str(brightness))
         logger.info("Global Brightness: {}% ({} nits)".format(brightness_pc,brightness_nits))
         logger.info ("RED: {}".format(rx_data[19]))
         logger.info ("GREEN: {}".format(rx_data[20]))
         logger.info ("BLUE: {}".format(rx_data[21]))
         logger.info ("vRED: {}".format(rx_data[22]))
         status[port]["brightnessLevelPC"] = brightness_pc
         status[port]["brightnessLevel"] = brightness
         status[port]["brightnessLevelNits"] = brightness_nits
         status[port]["redLevel"] = rx_data[19]
         status[port]["greenLevel"] = rx_data[20]
         status[port]["blueLevel"] = rx_data[21]
         status[port]["vRedLevel"] = rx_data[22]
      else:
         status[port]["brightnessLevelPC"] = "N/A"
         status[port]["brightnessLevel"] = "N/A"
         status[port]["brightnessLevelNits"] = "N/A"
         status[port]["redLevel"] = "N/A"
         status[port]["greenLevel"] = "N/A"
         status[port]["blueLevel"] = "N/A"
         status[port]["vRedLevel"] = "N/A"         
   else:
         logger.warning("No data available at the input buffer")
         status[port]["brightnessLevelPC"] = "N/A"
         status[port]["brightnessLevel"] = "N/A"
         status[port]["brightnessLevelNits"] = "N/A"
         status[port]["redLevel"] = "N/A"
         status[port]["greenLevel"] = "N/A"
         status[port]["blueLevel"] = "N/A"
         status[port]["vRedLevel"] = "N/A"

def get_cabinet_width(port):
# ---------------------------------------------------------------------------------------
# CABINET WIDTH
# ---------------------------------------------------------------------------------------
   logger = logging.getLogger(LOGGER_NAME)
   logger.info("Getting cabinet width...")
   check_cabinet_width_send = methods.checksum (COMMANDS["check_cabinet_width"])
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in check_cabinet_width_send))
   ser.write (check_cabinet_width_send)
   time.sleep (sleep_time)
   if ser.inWaiting()>0:
      response = ser.read(size=ser.inWaiting())
      rx_data = list(response)
      logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
      if check_response(rx_data):
          cabinet_width = int(rx_data[19]<<8) + int(rx_data[18])
      else:
         cabinet_width = 'N/A'
   else:
         logger.warning("No data available at the input buffer")
         cabinet_width = 'N/A'
   logger.info("Cabinet width (pixels): {} ".format(cabinet_width)) 

   return(cabinet_width)

def get_cabinet_height(port):
# ---------------------------------------------------------------------------------------
# CABINET HEIGHT
# ---------------------------------------------------------------------------------------   
   logger = logging.getLogger(LOGGER_NAME)
   logger.info("Getting cabinet height...")
   check_cabinet_height_send = methods.checksum (COMMANDS["check_cabinet_height"])
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in check_cabinet_height_send))
   ser.write (check_cabinet_height_send)
   time.sleep (sleep_time)
   if ser.inWaiting()>0:
      response = ser.read(size=ser.inWaiting())
      rx_data = list(response)
      logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
      if check_response(rx_data):
          cabinet_height = int(rx_data[19]<<8) + int(rx_data[18])
      else:
         cabinet_height = 'N/A'          
   else:
         logger.warning("No data available at the input buffer")
         cabinet_height = 'N/A'
   logger.info("Cabinet height (pixels): {} ".format(cabinet_height))

   return(cabinet_height)

def get_receiver_connected(port):
# ---------------------------------------------------------------------------------------
# CHECK CONNECTION TO RECEIVER CARD
# ---------------------------------------------------------------------------------------   
   logger = logging.getLogger(LOGGER_NAME)
   global receiver_card_found
   global no_of_receiver_cards
   COMMANDS["check_receiver_model"][8] = no_of_receiver_cards
   check_receiver_model_send = methods.checksum (COMMANDS["check_receiver_model"])
   ser.write (check_receiver_model_send)
   time.sleep (sleep_time)
   if ser.inWaiting()>0:
      response = ser.read(size=ser.inWaiting())
      rx_data = list(response)
      logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
      if check_response(rx_data):
         receiver_card_found = True
      else:
         receiver_card_found = False          
   else:
      logger.warning("No data available at the input buffer")
      receiver_card_found = False
   return receiver_card_found

def get_receiver_card_model(port):
   global no_of_receiver_cards
   global receiver_card_found
   logger = logging.getLogger(LOGGER_NAME)
   logger.info("Getting receiver card model")
   COMMANDS["check_receiver_model"][8] = no_of_receiver_cards
   check_receiver_model_send = methods.checksum (COMMANDS["check_receiver_model"])
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in check_receiver_model_send))
   ser.write (check_receiver_model_send)
   time.sleep (sleep_time)
   if ser.inWaiting()>0:
      status[port]["receiverCard"][no_of_receiver_cards]={}
      response = ser.read(size=ser.inWaiting())
      rx_data = list(response)
      logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
      if check_response(rx_data):
         if (rx_data[19]==0x45) and (rx_data[18]==0x06):
               model = 'Nova A4s'
         else:
               if (rx_data[19]==0x45) and (rx_data[18]==0x08):
                  model = 'Nova A5s'
               else:
                  if (rx_data[19]==0x45) and (rx_data[18]==0x0A):
                     model = 'Nova A7s'
                  else:
                     if (rx_data[19]==0x45) and (rx_data[18]==0x09):
                           model = 'Nova A8s'
                     else:
                           if (rx_data[19]==0x45) and (rx_data[18]==0x0F):
                              model = 'Nova MRV 366/ MRV 316'
                           else:
                              if (rx_data[19]==0x45) and (rx_data[18]==0x10):
                                 model = 'Nova MRV 328'
                              else:
                                 if (rx_data[19]==0x45) and (rx_data[18]==0x0E):
                                       model = 'Nova MRV 308'
                                 else:
                                       if (rx_data[19]==0x46) and (rx_data[18]==0x21):
                                          model = 'Nova A5s Plus'
                                       else:
                                          model =('{}'.format(hex(rx_data[19]),hex(rx_data[18])))
      else:
          model = 'N/A'
      status[port]["receiverCard"][no_of_receiver_cards]["receiverModel"]=model
      logger.info ('Receiver card model: {}'.format(model))
   else:
      logger.warning("No data available at the input buffer")
      receiver_card_found = False
   return

def get_receiver_card_firmware(port):
# ---------------------------------------------------------------------------------------
# RECEIVER CARD FW VERSION
# ---------------------------------------------------------------------------------------
   global no_of_receiver_cards
   logger = logging.getLogger(LOGGER_NAME)
   logger.info("Getting receiver card firmware")
   COMMANDS["check_receiver_fw"][8] = no_of_receiver_cards
   check_receiver_fw_send = methods.checksum (COMMANDS["check_receiver_fw"])
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in check_receiver_fw_send))
   ser.write (check_receiver_fw_send)
   time.sleep (sleep_time)
   if ser.inWaiting()>0:
         response = ser.read(size=ser.inWaiting())
         rx_data = list(response)
         logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
         if check_response(rx_data):
            FPGA=str(rx_data[18])+'.'+str(rx_data[19])+'.'+str(rx_data[20])+'.'+str("{:02x}".format(rx_data[21]))
         else:
            FPGA="N/A" 
   else:
         logger.warning("No data available at the input buffer")
         FPGA="N/A"
   status[port]["receiverCard"][no_of_receiver_cards]["receiverFPGA"]=FPGA
   logger.info('Receiver Card FPGA Firmware version: {}'.format(FPGA))

def get_receiver_temp_voltage(port):
# ---------------------------------------------------------------------------------------
# CHECK TEMPERATURE, VOLTAGE & MONITORING
# Retrieve data for receiver cards
# Maximum resolution: 512 x 384 px @60Hz
# AC/DC: MEGMEET MCP260WL-4.5 / Output 4.5VDC 40A (4.2~5.0V)
# A5s PLUS
# Input voltage: 3.8 to 5.5 V
# Rated current: 0.6A
# Rated power consumption: 3.0 W
# Operating Temperature: -20C to 70C
#
# Device: Receiving Card 
# Base Address: 0a000000 H 
# Data Length: 100H
# ---------------------------------------------------------------------------------------
   global no_of_receiver_cards
   logger = logging.getLogger(LOGGER_NAME)
   logger.info("Getting receiver card monitoring, temperature and voltage")
   COMMANDS["check_monitoring"][8] = no_of_receiver_cards
   check_monitoring_send = methods.checksum (COMMANDS["check_monitoring"])
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in check_monitoring_send))
   ser.write(check_monitoring_send)
   time.sleep(sleep_time)
   if ser.inWaiting()>0:
         response = ser.read(size=ser.inWaiting())
         rx_data = list (response)
         logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
         if check_response(rx_data):
            if ((rx_data[18] & 0x80))==0x80:
               if (rx_data[18]&0x1)==0:
                  sign = ""
               else:
                  sign = "-"
               logger.info("Temperature (valid): {}{:.1f}°C ({})".format(sign,(rx_data[19]&0xFE)*0.5,hex(rx_data[19])))
               temp_valid="Yes"
               temperature = sign+str((rx_data[19]&0xFE)*0.5)
               temperature = round(float(temperature), 2)
            else:
               logger.info ("Temperature data invalid")
               temp_valid="No"
               temperature="N/A"
            
            if ((rx_data[21]) & 0x80)==0x80:
               logger.info("Voltage (valid): {:.1f}V ({})".format(0.1*(rx_data[21]&0x7F),hex(rx_data[21])))
               voltage_valid="Yes"
               voltage=0.1*(rx_data[21]&0x7F)
               voltage = round(float(voltage), 2)#
            else:
               logger.info ("Voltage data invalid")
               voltage_valid="No"
               voltage="N/A"

            if (rx_data[50]==0xFF):
               logger.info ("Monitoring card available ({})".format(hex(rx_data[50])))
               monitoring_card="Yes"
            else:
               logger.info ("Monitoring card unavailable ({})".format(hex(rx_data[50])))
               monitoring_card="No"
         else:
            temp_valid="N/A"
            temperature="N/A"
            voltage_valid="N/A"
            voltage="N/A"
            monitoring_card="N/A"          
   else:
         logger.info ("No data available at the input buffer")
         temp_valid="N/A"
         temperature="N/A"
         voltage_valid="N/A"
         voltage="N/A"
         monitoring_card="N/A"
   status[port]["receiverCard"][no_of_receiver_cards]["tempValid"]=temp_valid
   status[port]["receiverCard"][no_of_receiver_cards]["temperature"]=temperature
   status[port]["receiverCard"][no_of_receiver_cards]["voltageValid"]=voltage_valid
   status[port]["receiverCard"][no_of_receiver_cards]["voltage"]=voltage
   status[port]["receiverCard"][no_of_receiver_cards]["monitorCard"]=monitoring_card

def get_cabinet_kill_mode(port):
#-------------------------------------------------------------------------
# CHECK KILL MODE (CABINET STATUS)
# This is essentially information about whether the display is ON or OFF
#-------------------------------------------------------------------------
   global no_of_receiver_cards
   logger = logging.getLogger(LOGGER_NAME)
   logger.info("Getting cabinet kill mode (on/off)")
   COMMANDS["kill_mode"][8] = no_of_receiver_cards
   kill_mode_send = methods.checksum(COMMANDS["kill_mode"])
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in kill_mode_send))
   ser.write (kill_mode_send)
   time.sleep (sleep_time)
   if ser.inWaiting()>0:
         response = ser.read(size=ser.inWaiting())
         rx_data = list(response)
         logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
         if check_response(rx_data):
            if (rx_data[18]==0x00):
               logger.info ("Cabinet Operating Status (Kill mode): ON")
               kill="On"
               cabinet_on = True
            else:
               if (rx_data[18]==0xFF):
                  logger.info ("Cabinet Operating Status (Kill mode): OFF")
                  kill="Off"
                  cabinet_on = False
               else:
                  logger.info ("Cabinet Operating Status (Kill mode): UNKNOWN")
                  kill="Unknown"
                  cabinet_on = False
         else:
            kill="N/A"
            cabinet_on = False
   else:
         logger.info ("No data available at the input buffer")
         kill="N/A"
         cabinet_on = False
   status[port]["receiverCard"][no_of_receiver_cards]["kill"]=kill
   return cabinet_on

def get_cabinet_lock_mode(port):
#----------------------------------------------------------
# CHECK LOCK MODE
#----------------------------------------------------------
   global no_of_receiver_cards
   logger = logging.getLogger(LOGGER_NAME)
   logger.info("Getting cabinet lock mode (normal/locked)")
   COMMANDS["lock_mode"][8] = no_of_receiver_cards
   lock_mode_send = methods.checksum(COMMANDS["lock_mode"])
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in lock_mode_send))
   ser.write (lock_mode_send)
   time.sleep (sleep_time)
   if ser.inWaiting()>0:
         response = ser.read(size=ser.inWaiting())
         rx_data = list(response)
         logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
         if check_response(rx_data):
            if (rx_data[18]==0x00):
               logger.info ("Cabinet Lock Mode: NORMAL")
               lock="Normal"
            else:
               if (rx_data[18]==0xFF):
                  logger.info ("Cabinet Lock Mode: LOCKED")
                  lock="Locked"
               else:
                  logger.info ("Cabinet Lock Mode: UNKNOWN")
                  lock="Unknown"
         else:
            lock="N/A" 
   else:
         logger.warning ("No data available at the input buffer")  
         lock="N/A"
   status[port]["receiverCard"][no_of_receiver_cards]["locked"]=lock

def get_gamma_value(port):
#----------------------------------------------------------------
# GAMMA VALUE
# Device: Receiving Card
# Base Address: 02000000 H 
# Data Length: 1H
#----------------------------------------------------------------
   global no_of_receiver_cards
   logger = logging.getLogger(LOGGER_NAME)
   logger.info("Getting cabinet gamma value")
   gamma_value_send = methods.checksum(COMMANDS["gamma_value"])
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in gamma_value_send))
   ser.write (gamma_value_send)
   time.sleep (sleep_time)
   if ser.inWaiting()>0:
         response = ser.read(size=ser.inWaiting())
         rx_data = list(response)
         logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
         if check_response(rx_data):
            gamma = rx_data[18]/10
         else:
            gamma = 'N/A' 
   else:
            logger.warning ("No data available at the input buffer")
            gamma = 'N/A'
   logger.info ("Gamma Value: {}".format(gamma))
   status[port]["receiverCard"][no_of_receiver_cards]["gamma"]=gamma

def get_module_flash(port,  modules_ok):
#-----------------------------------------------------------------
# MODULE FLASH CHECK
# https://www.youtube.com/watch?v=-h26LV6cIwc - Novastar Memory on Module
# https://www.youtube.com/watch?v=W7U5sa4lxFY - NovaLCT Performance Settings and Receiving Card Configuration Files
# https://www.youtube.com/watch?app=desktop&v=XQJlwXRE5rE&fbclid=IwAR2dWGKc2lAKW4E-qGxyRxprmdLnaWo52XoPRNXpSX8GQNmv_QIyP9RTyKI - Smart settings for a regular module
#---------------------------------------------------------------------------------------
   global no_of_receiver_cards
   logger = logging.getLogger(LOGGER_NAME)
   logger.info("Sending module flash request and wait")
   COMMANDS["start_check_module_flash"][8] = no_of_receiver_cards
   start_check_module_flash_send = methods.checksum(COMMANDS["start_check_module_flash"])
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in start_check_module_flash_send))
   ser.write (start_check_module_flash_send)
   time.sleep (sleep_time)
   if ser.inWaiting()>0:
         response = ser.read(size=ser.inWaiting())
         rx_data = list (response)
         logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
         if check_response(rx_data):
            time.sleep(flash_wait_time) # this may have to be more than 1 second and perhaps minuimum 20s
         else:
            logger.error('ERROR')
   else:
         logger.warning ("No data available at the input buffer")
   # ------------------------------------------------------------------------------------------
   # MODULE READ BACK DATA
   # ------------------------------------------------------------------------------------------
   logger.info("Getting module flash data")
   COMMANDS["read_back_module_flash"][8] = no_of_receiver_cards
   read_back_module_flash_send = methods.checksum(COMMANDS["read_back_module_flash"])
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in read_back_module_flash_send))
   ser.write(read_back_module_flash_send)
   time.sleep(sleep_time)
   modules_ok = True
   if ser.inWaiting()>0:
         response = ser.read(size=ser.inWaiting())
         rx_data = list (response)
         logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
         number_of_modules = int(rx_data[16]/4)
         logger.info ("Total amount of modules: {}".format(number_of_modules))
         status[port]["receiverCard"][no_of_receiver_cards]["module"]={}
         if check_response(rx_data):
            for j in range (int(number_of_modules)):
               status[port]["receiverCard"][no_of_receiver_cards]["module"][j]={}
               element = rx_data[18+j*4:(18+j*4)+4]
               if (element[0]==0x5):
                  module_sts= "OK"
                  modules_ok = modules_ok and True
               else:
                  if (element[0]==0x3):
                     module_sts = "Error or no module flash available"
                     modules_ok = modules_ok and False
                  else:
                     module_sts = "Unknown module state"
                     modules_ok = modules_ok and True
               if element[1]==0x05:
                  module_ack= "OK"
                  modules_ok = modules_ok and True
               else:
                  if (element[0]==0x3):
                     module_ack = "Error or no module flash available"
                     modules_ok = modules_ok and False
                  else:
                     module_ack = "Unknown module state"
                     modules_ok = modules_ok and True      
               if (element[0]==0x05 and element[1]==0x05):
                   module_status = "OK"
                   modules_ok = modules_ok and True 
               else:
                   if (element[0]==0x03 or element[1]==0x03):
                       module_status = "Error or no module flash available"
                       modules_ok = modules_ok and False 
                   else:
                       module_status = "Unknown module state" 
                       modules_ok = modules_ok and True 
               logger.info ("Module {module_index}: STATUS:{write_result} (0x{write_hex:02X}), ACKNOWLEDGE:{read_result} (0x{read_hex:02X})".format(module_index=j+1,write_result=module_sts,write_hex=element[0],read_result=module_ack,read_hex=element[1]))#.format(j+1).format(module_write).format(element[0]).format(module_read).format(element[1]))
               status[port]["receiverCard"][no_of_receiver_cards]["module"][j]=module_status
         else:
            modules_ok = modules_ok and False
            status[port]["receiverCard"][no_of_receiver_cards]["module"]='N/A'
   else:
         logger.warning ("No data available at the input buffer")    
         number_of_modules = 0
         modules_ok = modules_ok and False
         module_status="N/A"    
         status[port]["receiverCard"][no_of_receiver_cards]["module"]="N/A"
   return (number_of_modules,modules_ok)

def get_ribbon_cable_status(port):
# ------------------------------------------------------------------------------------------
# RIBBON CABLE
# Ribbon cable detection must work together with MON300 monitoring card.
# Device: ScanCard
# Base Address: 0x0210_0000H 
# Data Length: 2H
# https://www.youtube.com/watch?v=h4grZUyoQyE - Exchange Data Group
# Detect the status of 128 pins of the monitor card. The results of each signal line are 
# expressed in 1bit, 0 represents OK, and 1 is error. Total 16 bytes
# The order is
# Group0 (0-3)...Group15 (0-3) 
# ->A (0-7) ->B (0-7) ->C (0-7) ->D (0-7) 
# ->LAT (0-7) ->OE (0-7) ->DCLK (0-7) ->CTRL (0-7).
# ------------------------------------------------------------------------------------------
   global no_of_receiver_cards
   logger = logging.getLogger(LOGGER_NAME)
   logger.info("Getting ribbon cable status...[TODO]")
   COMMANDS["ribbon_cable"][8] = no_of_receiver_cards
   ribbon_cable_send = methods.checksum (COMMANDS["ribbon_cable"])
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in ribbon_cable_send))
   ser.write(ribbon_cable_send)
   time.sleep(sleep_time)
   if ser.inWaiting()>0:
         response = ser.read(size=ser.inWaiting())
         rx_data = list (response)
         logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
         if check_response(rx_data):
            data=rx_data[18:34]
            k=0
            for x in range(8):
               logger.info ("G{firstByte}, G{secondByte} = {one:04b}, {two:04b}".format(firstByte=k, secondByte=k+1, one=data[x]>>4, two=data[x] & 0x0F))
               status[port]["receiverCard"][no_of_receiver_cards]["G{firstByte}, G{secondByte}".format(firstByte=k, secondByte=k+1)]="{one:04b}, {two:04b}".format(one=data[x]>>4, two=data[x] & 0x0F)
               k=k+2
            logger.info("A = {:08b}".format(data[8]))
            status[port]["receiverCard"][no_of_receiver_cards]["A"]="{:08b}".format(data[8])    
            logger.info("B = {:08b}".format(data[9]))
            status[port]["receiverCard"][no_of_receiver_cards]["B"]="{:08b}".format(data[9])   
            logger.info("C = {:08b}".format(data[10]))
            status[port]["receiverCard"][no_of_receiver_cards]["C"]="{:08b}".format(data[10])
            logger.info("D = {:08b}".format(data[11]))
            status[port]["receiverCard"][no_of_receiver_cards]["D"]="{:08b}".format(data[11])    
            logger.info("LAT = {:08b}".format(data[12]))
            status[port]["receiverCard"][no_of_receiver_cards]["LAT"]="{:08b}".format(data[12])
            logger.info("OE = {:08b}".format(data[13]))
            status[port]["receiverCard"][no_of_receiver_cards]["OE"]="{:08b}".format(data[13])
            logger.info("DCLK = {:08b}".format(data[14]))
            status[port]["receiverCard"][no_of_receiver_cards]["DCLK"]="{:08b}".format(data[14])
            logger.info("CTRL = {:08b}".format(data[15]))
            status[port]["receiverCard"][no_of_receiver_cards]["CTRL"]="{:08b}".format(data[15])
         else:
            logger.error('ERROR') 
   else:
         logger.warning ("No data available at the input buffer")

def get_edid(port): #inactive
# -----------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------
   global no_of_receiver_cards
   logger = logging.getLogger(LOGGER_NAME)
   logger.info("Getting EDID 1.3 register")
   edid_send = methods.checksum(COMMANDS["edid_register"])
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in edid_send))
   ser.write (edid_send)
   time.sleep (sleep_time)
   if ser.inWaiting()>0:
         response = ser.read(size=ser.inWaiting())
         rx_data = list(response)
         logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
         #if check_response(rx_data):
            #print('OK')
         # -----------------------------------------------------------------------------------------------
         # PARSE EDID information
         #chksum=0
         #edid = rx_data[18:145]
         #for a in edid:
         #   chksum=a+chksum
         #chksum=(0xFF00-chksum) & (0xFF)
         #print ('{:02X}'.format(chksum))
         #edid.append(chksum)
         #edid_hex = ' '.join('{:02X}'.format(a) for a in edid)
         #edid = pyedid.parse_edid(edid_hex)#print ('\n'+edid_hex)
         #json_str = str(edid) # making JSON string object
         #print(json_str)

         # returned Edid object, used the Default embedded registry
         #edid_hex='00 FF FF FF FF FF FF 00 39 F6 05 04 13 06 28 00 10 17 01 03 81 1E 17 B4 EA C1 E5 A3 57 4E 9C 23 1D 50 54 21 08 00 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 5B 36 80 A0 70 38 23 40 30 20 36 00 CB 28 11 00 00 1E 00 00 00 FF 00 4E 4F 56 41 53 54 41 52 4D 33 00 00 00 00 00 00 FC 00 4D 41 52 53 A3 44 49 53 50 4C 41 59 00 00 00 00 FD 00 30 7B 1C C8 11 00 0A 20 20 20 20 20 20 00 C7'
         #edid_hex = '00 FF FF FF FF FF FF 00 39 F6 05 04 00 00 00 00 10 17 01 03 81 1E 17 AA EA C1 E5 A3 57 4E 9C 23 1D 50 54 BF EE 00 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 5B 36 80 A0 70 38 23 40 30 20 36 00 CB 28 11 00 00 18 00 00 00 FF 00 4E 4F 56 41 53 54 41 52 4D 33 00 00 00 00 00 00 FC 00 4E 4F 56 41 20 48 44 20 43 41 52 44 00 00 00 00 FD 00 30 7B 1C C8 11 00 0A 20 20 20 20 20 20 01 65'
         #print (edid)
         # -----------------------------------------------------------------------------------------------
   else:
            logger.warning ("No data available at the input buffer")
            #edid = 'N/A'
   #logger.info ("EDID: {}".format(gamma))
   #status[port]["receiverCard"][no_of_receiver_cards]["gamma"]=gamma

def get_receiver_brightness(port):
# ---------------------------------------------------------------------------------------
# SCREEN BRIGHTNESS SETTINGS
# This needs to be on a per receiver card basis or global?
# -----------------------------------------------------------------------------------------------
    global no_of_receiver_cards
    logger = logging.getLogger("LOGGER_NAME")
    
    logger.info("Getting current receiver card brightness...[TO CHECK]")
    
    COMMANDS["get_brightness"][8] = no_of_receiver_cards
    get_brightness_send = methods.checksum(COMMANDS["get_brightness"])
    
    logger.debug("Sending command: " + ' '.join('{:02X}'.format(a) for a in get_brightness_send))
    
    ser.write(get_brightness_send)
    time.sleep(sleep_time)

    if ser.inWaiting() > 0:
        response = ser.read(size=ser.inWaiting())
        rx_data = list(response)
        
        logger.debug("Received data: " + ' '.join('{:02X}'.format(a) for a in rx_data))

        if check_response(rx_data):
            brightness = rx_data[18]
            brightness_pc = round(100 * brightness / 255)
            
            red = rx_data[19]
            green = rx_data[20]
            blue = rx_data[21]
            vRed = rx_data[22]

            logger.info(f"Brightness Level: {brightness}")
            logger.info(f"Global Brightness: {brightness_pc}%")
            logger.info(f"RED: {red}, GREEN: {green}, BLUE: {blue}, vRED: {vRed}")

            status[port]["receiverCard"][no_of_receiver_cards] = {
                "brightnessLevelPC": brightness_pc,
                "brightnessLevel": brightness,
                "redLevel": red,
                "greenLevel": green,
                "blueLevel": blue,
                "vRedLevel": vRed
            }
            return brightness_pc, brightness, red, green, blue, vRed  # ✅ Return values
        else:
            logger.warning("Invalid response received.")

    else:
        logger.warning("No data available at the input buffer")

    # If no data or invalid response, return "N/A"
    status[port]["receiverCard"][no_of_receiver_cards] = {
        "brightnessLevelPC": "N/A",
        "brightnessLevel": "N/A",
        "redLevel": "N/A",
        "greenLevel": "N/A",
        "blueLevel": "N/A",
        "vRedLevel": "N/A"
    }
    return "N/A", "N/A", "N/A", "N/A", "N/A", "N/A"

def get_display_brightness(port):
# ---------------------------------------------------------------------------------------
# SCREEN BRIGHTNESS SETTINGS
# This needs to be on a per receiver card basis or global?
# ---------------------------------------------------------------------------------------
   logger = logging.getLogger(LOGGER_NAME)
   logger.info("Getting current screen brightness...[TO CHECK]")
   display_brightness_send = methods.checksum(COMMANDS["display_brightness"])
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in display_brightness_send))
   ser.write (display_brightness_send)
   time.sleep (sleep_time)
   if ser.inWaiting()>0:
      response = ser.read(size=ser.inWaiting())
      rx_data = list(response)
      logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
      if check_response(rx_data):
         brightness = rx_data[18]
         brightness_pc = round(100*brightness/255)
         logger.info("Brightness Level: "+ str(brightness))
         logger.info("Global Brightness: {}% ".format(brightness_pc))
         status[port]["brightnessLevelPC"] = brightness_pc
         status[port]["brightnessLevel"] = brightness
      else:
         status[port]["brightnessLevelPC"] = "N/A"
         status[port]["brightnessLevel"] = "N/A"
   else:
         logger.warning("No data available at the input buffer")
         status[port]["brightnessLevelPC"] = "N/A"
         status[port]["brightnessLevel"] = "N/A"

def get_redundant_status(port):
# ---------------------------------------------------------------------------------------
# REDUNDANCY CHECK
# Device: Sending Card
# Base Address: 0x0200_0000 H 
# Data Length: 1H
# Offset: 1E
# ---------------------------------------------------------------------------------------
   logger = logging.getLogger(LOGGER_NAME)
   logger.info("Getting redundancy status")
   check_redundancy_send = methods.checksum(COMMANDS["check_redundancy"])
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in check_redundancy_send))
   ser.write (check_redundancy_send)
   time.sleep (sleep_time)
   if ser.inWaiting()>0:
      response = ser.read(size=ser.inWaiting())
      rx_data = list(response)
      logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
      if check_response(rx_data):
         logger.info ("Port 1: {:02b}".format(int(rx_data[18]) & 3))
         logger.info ("Port 2: {:02b}".format(int(rx_data[18]) & 12))
         logger.info ("Port 3: {:02b}".format(int(rx_data[18]) & 48))
         logger.info ("Port 4: {:02b}".format(int(rx_data[18]) & 192))
   else:
         logger.warning("No data available at the input buffer")

def get_function_card(port):
# ---------------------------------------------------------------------------------------
# DETERMINE MULTIFUNCTION CARD MODEL
# Check which multifunction card hardware model is connected.
# ---------------------------------------------------------------------------------------
   logger = logging.getLogger(LOGGER_NAME)
   logger.info("Getting function card model")
   function_card_model_send = methods.checksum(COMMANDS["check_function_card"])
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in function_card_model_send))
   ser.write (function_card_model_send)
   time.sleep (sleep_time)
   if ser.inWaiting()>0:
      response = ser.read(size=ser.inWaiting())
      rx_data = list(response)
      logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
      if check_response(rx_data):
         if (rx_data[18]==1 and rx_data[19]==0x81):
            model="MFN300/MFN300-B"
         else:
             model="Unknown"
      else:
          model="N/A"
   else:
      logger.warning("No data available at the input buffer")
      model="N/A"
   status[port]["functionCardModel"] = model
   logger.info("Function card model: " + model)
   return (model)

def get_module_status(port):
# ---------------------------------------------------------------------------------------
# MODULE STATUS
# REFERENCE: PROTOCOL FOR RETRIEVING MODULE STATUS
# 
# Function is to obtain the status information from a recieving card. 
# Includes instruction for reading module status' Flat cable status, power supply voltage
# Assumptions: Modules are referring to panels, number of data groups per module is 1. Both of these values
#              are used to calculate the length of data to be read.
# -----------------------------------------------------------------------------------------------
   global no_of_receiver_cards
   flag_module_error = False
   # ASSUMPTIONS:
   data_groups_per_module = 1 
   no_of_modules = 4
   
   logger = logging.getLogger(LOGGER_NAME)

   reciever_card_range = range(no_of_receiver_cards)
   for reciever_card in reciever_card_range:
      logger.info(f"Getting receiver card number {reciever_card} status")
      COMMANDS["get_status"][8] = reciever_card 
      response_length = ( no_of_modules * ( 22 + 2 * data_groups_per_module ) )
      logger.debug(f"Data Size: {response_length}")
      first_byte = response_length & 0xFF00
      second_byte = response_length & 0x00FF
      print (first_byte, second_byte)
      COMMANDS["get_status"][16] = second_byte
      COMMANDS["get_status"][17] = first_byte
      COMMANDS["get_status"][16] = response_length
      get_status_send = methods.checksum(COMMANDS["get_status"])
      logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in get_status_send))
      ser.write (get_status_send)
      time.sleep (sleep_time)
      if ser.inWaiting()>0:
         response = ser.read(size=ser.inWaiting())
         logger.debug("Received data size: " + str(len(response)))
         rx_data = list(response)

      #TESTING CODE 
      #expected_hex = "AA5500C400FE0100010000000A00000A7800FF8028ADB073160200000000000000000000000000008001800180018001FF8026AD245C140200000000000000000000000000008001800180018001FF802AADA481140200000000000000000000000000008001800180018001FF8024AC1455000000000000000000000000000000008001800180018001756C"
      #expected_bytes = bytes.fromhex(expected_hex)
      #rx_data = list(expected_bytes)

      #logger.info(f"expected_bytes {expected_bytes}")
      #logger.info(f"rx_data: {rx_data}")

      logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
      data_size = (len(rx_data))
      logger.debug(f"Response Data Size: {data_size}")
      
      if check_response(rx_data):
         # Initialize the dictionary to store each module's data
         modules = {}
         # List to store flat cable data
         flat_cable_data = []

         start_index = 18

         # Extract 24 bytes for the first module's data
         module_1_end_index = start_index + 22
         modules["module_1_data"] = (rx_data[start_index:module_1_end_index], 1)
         start_index = module_1_end_index  # Move start index to the end of the first module's data

         # Extract 2 * num_of_modules bytes for flat cable data 
         flat_cable_end_index = start_index + (2 * no_of_modules)
         flat_cable_data = rx_data[start_index:flat_cable_end_index]
         start_index = flat_cable_end_index  # Move start index to end of flat cable data

         # Extract 24 bytes for each additional module's data
         for i in range(1, no_of_modules):
            module_end_index = start_index + 22
            modules[f"module_{i + 1}_data"] = (rx_data[start_index:module_end_index], i + 1)
            start_index = module_end_index + (2 * no_of_modules)  # Move to the next 24-byte module segment, the index then skips over the flat cable data

         logger.debug("Modules Data:")
         for module_name, (data, module_number) in modules.items():
            logger.debug(f"{module_name}: {data}, Number: {module_number}")

         # Mapping of bit position to corresponding signal line names
         signal_lines = {
            0: "E",
            1: "LAT",
            2: "OE",
            3: "DCLK",
            4: "CTRL",
            5: "RFU",
            6: "RFU",  
            7: "RFU",
            8: "R",      
            9: "G",
            10: "B",
            11: "RFU",  
            12: "A",
            13: "B",   
            14: "C",
            15: "D"
         }

         #Check each module
         for module_name, (modules, module_number) in modules.items():
            #LED Module status check
            logger.debug(f"Reciever Card {reciever_card}")
            module_status = modules[0]
            if (module_status == 0xFF):
               logger.debug(f"   Module {module_number} is functioning")
            elif (module_status == 0x00):
               logger.error(f"   Module {module_number} is not functioning correctly")
               flag_module_error = True
            else:
               logger.error(f"   Module {module_number} Detection error")
               flag_module_error = True

         # This loop will handle each module's flat cable data by checking 2 bytes per module
         for module_index in range(no_of_modules):
            byte1, byte2 = flat_cable_data[module_index * 2: module_index * 2 + 2]
            module_number = module_index + 1
            for byte_index, byte in enumerate([byte1, byte2]):
               for bit_position in range(8):
                     if (byte >> bit_position) & 1:
                        line_index = byte_index * 8 + bit_position
                        line_name = signal_lines.get(line_index, "Unknown Line")
                        logger.error(f"Fault detected in module {module_number} Line: {line_name}")

         # Log the overall status of modules
         if flag_module_error:
            logger.info("  One or more modules reported faults.")
         else:
            logger.info("All modules are functioning correctly.")  
      else:
            logger.warning("No data available at the input buffer")