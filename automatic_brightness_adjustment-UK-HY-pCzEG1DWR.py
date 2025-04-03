#!/usr/bin/env python3
#------------------------------------------------------------------------------------------------------------
# CHECK DISPLAY STATUS VIA NOVASTAR SENDER AND RECEIVER
# Please read the README.TXT file for further information and details.
#
# USAGE
# Windows: python display_status.py & echo %errorlevel%
# Linux: python display_status.py ;echo $?
#
# DESCRIPTION
# - A one-shot Python script which queries a number of parameters from a Novstar sender/control system
# - Script should be run at regular intervals, for example every 20 minutes
# - (TELEMETRY) Resulting values written into status.json file
# - (STATUS) Script outputs a string indicating current screen status and and exit code corresponding to the monitoring agent (e.g. Icinga) expected codes (0,1,2,3)
# - Additional data is written into debug.log and allows deep investigation on issues (mainly communications with controller)
# - The display configuration is stored into config.json file
# - The communications protocol configuration data is stored in config.json
# - ALS transition take circa 2m 30s (per step? TBC)
#
# ERROR CODES
# - 0 = OK - display is in normal working order: all vital parameters as expected
# - 1 = WARNING - vital parameters returning abnormal values or anomaly
#       ! sender card not detected
#       ! DVI input not valid
#       ! receiver cards not detected or missing
#       ! kill mode OFF
#       ! faulty modules
#       + ribbon cables
#       + brightness sensor not detected
#       + brightness level low
#       + temperature warning
#       + voltage warning
#       + test mode
# - 2 = CRITICAL - display is not showing content correctly or at all
# - 3 = UNKNOWN - any other event
#
# KNOWN BUGS OR ISSUES
#
# ------------------------------------------------------------------------------------------------------------
# IMPORTS

import serial
import sys
import time
import serial.tools.list_ports
import logging
from logging.handlers import TimedRotatingFileHandler
import datetime
from datetime import datetime, timedelta, timezone
import json
import methods
from methods import read_data, write_data, loadConfig
from pathlib import Path
# ------------------------------------------------------------------------------------------------------------
# DEFINITIONS AND INITIALISATIONS

# LOGGER
FORMATTER = logging.Formatter('%(asctime)s %(name)s %(levelname)-8s %(message)s', datefmt='%d/%m/%Y %H:%M:%S')
SCRIPT_DIR = Path(__file__).parent.resolve()
LOG_FILE = str(SCRIPT_DIR / "debug.log")  # Convert Path object to string
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
"check_receiver_fw" : list (b"\x55\xAA\x00\x32\xFE\x00\x01\x00\x00\x00\x00\x00\x04\x00\x00\x08\x04\x00\x96\x56"), #A valid Firmware version is a value other than 00 00 00 00
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
"set_brightness": list(b"\x55\xAA\x00\x14\xFE\x00\x01\x00\xFF\xFF\x01\x00\x01\x00\x00\x02\x05\x00\x80\x80\x80\x80\x80\x70\x56"),  # get receiver brightness
#################################################################################################
}
# ------------------------------------------------------------------------------------------------------------
# MAIN
def main():
    global sleep_time
    global flash_wait_time
    #global status 
    global ser
    global last_updated
    global data
    global no_of_receiver_cards
    global receiver_card_found
    global number_of_modules
    global brightness_adjustment_complete
    global minute_tolerance
    global off_time
    testing = True
    EXIT_CODE = UNKNOWN
    my_logger = methods.get_logger(LOGGER_NAME,LOG_FILE,FORMATTER,LOGGER_SCHEDULE,LOGGER_INTERVAL,LOGGER_BACKUPS) # Set up the logging
    my_logger.info("*********************************************************************************************************************************************")
    my_logger.info("5Eyes - Starting Display Status Checks")
    config = loadConfig(LOGGER_NAME) # Load the configuration information
    #my_logger.info("Version: {}, Baudrate: {}, Sleep Time: {}, Flash Timeout: {}".format(config["version"],config["baudrate"],config["sleepTime"],config["flashWaitTime"]))
    last_updated = datetime.now().strftime("%d/%m/%Y %H:%M")
    sleep_time = float(config["sleep_time"])
    flash_wait_time = float(config["flash_wait_time"])
    data = read_data("status.json",LOGGER_NAME)
    #status = {} # Initialise variable to store status data\
    modules_ok = True # assume all modules are ok to start off
    ser = methods.setupSerialPort(config["baudrate"],LOGGER_NAME) # Initialise serial port
    device_found, valid_ports = search_devices()
    brightness_adjustment_complete = False
    minute_tolerance = 5 # Tolerance applied to sunrise, sunset, dawn, and dusk times
    if (testing):
      my_logger.info("********** TESTING MODE IS SET **********")
      time_interval = 1 # This is the interval that the brightness will be adjusted
    else:
      time_interval = 5 # This is the interval that the brightness will be adjusted 
    if (device_found!=0):
        i=0
        for serial_port in sorted(valid_ports):
            my_logger.info("*******************    DEVICE {}   *******************".format(i))
            my_logger.info("Connecting to device on {}".format(serial_port))
            ser.port = serial_port
            try: 
               ser.open()
            except Exception as e:
               my_logger.error("Error opening serial port: " + ser.name + " - " + str(e))
            if ser.isOpen():
               try:
                  ser.flushInput() #flush input buffer, discarding all its contents
                  ser.flushOutput() #flush output buffer, aborting current output and discard all that is in buffer
                  my_logger.info("Opened device on port: " + ser.name) # remove at production
               except Exception as e1:
                  my_logger.error("Error opening serial port: " + str(e))
            else:
               my_logger.error("Error communicating with device: " + ser.name)
            # -------------------------------------
            # RETRIEVE PARAMETERS FROM SENDER CARDS
            # -------------------------------------
            model = get_sender_card_model(serial_port)
            DVI = get_DVI_signal_status(serial_port)
            # -------------------------------------
            receiver_card_found = True
            no_of_receiver_cards = 0
            #status[serial_port]["receiverCard"]={}
            display_on = True
            ##############################################################################################
            # CODE BELOW SHOULD BE INSIDE A FOR LOOP
            # THIS IS TO MAKE SURE EACH PORT OF THE SENDER CARD IS CHECKED
            # FOR MCTRL600/610 THESE ARE 4 PORTS
            # FOR MCTRL300 THESE ARE ONLY 2
            # ANY RECEIVER CARDS CONNECTED TO PORTS 1-4 SHOULD RESPOND WITH DATA - IF NOT, EITHER NOTHING ATTACHED OR ERROR
            # - Index should be passed into function as parameter
            # - New command should be created accounting for different data port number
            ##############################################################################################
            if (model == "MSD600/MCTRL600/MCTRL610/MCTRL660"):
               no_of_rxcardports = 4
            else:
               no_of_rxcardports = 2

            daylight_times = read_daylight_times()
            sunset_time = daylight_times.get("sunset_time")
            dusk_time = daylight_times.get("dusk_time")
            dawn_time = daylight_times.get("dawn_time")
            sunrise_time = daylight_times.get("sunrise_time")
            my_logger.debug(f"Sunrise Time:  {sunrise_time}")
            my_logger.debug(f"Sunset Time:   {sunset_time}")

            # Convert string timestamps to datetime objects
            #sunrise_time = datetime.fromisoformat(daylight_times.get("sunrise"))
            #sunset_time = datetime.fromisoformat(daylight_times.get("sunset"))
            # Add 30 minutes to sunrise_time
            sunrise_time = sunrise_time + timedelta(minutes=30)
            # Subtract 30 minutes from sunset_time
            sunset_time = sunset_time - timedelta(minutes=30)

            my_logger.debug(f"Sunrise Time Adjusted:  {sunrise_time}")
            my_logger.debug(f"Sunset Time Adjusted:   {sunset_time}")

            current_time = datetime.now(timezone.utc)

            # TESTING to be removed:
            if (testing):
               #current_time = current_time.replace(hour=1, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
               #sunset_time = datetime.now(timezone.utc) - timedelta(minutes=3)
               #dusk_time = datetime.now(timezone.utc) + timedelta(minutes=3)
               dawn_time = datetime.now(timezone.utc) - timedelta(minutes=3)
               sunrise_time = datetime.now(timezone.utc) + timedelta(minutes=3)

            while (receiver_card_found or not brightness_adjustment_complete) and not (receiver_card_found and brightness_adjustment_complete):

                  for port_value in range(0, no_of_rxcardports):
                     my_logger.debug(f"*********** Port: {port_value} Set ***********")
                  
                     for command_name, command_template in COMMANDS.items():
                        COMMANDS[command_name][7] = port_value 

                     my_logger.info("*********** AUTOMATIC BRIGHTNESS ADJUSTMENT ***********")
                     my_logger.info ("Connecting to receiver number: {}".format(no_of_receiver_cards))    
                     if (not get_receiver_connected(serial_port)):  
                        my_logger.info("Receiver card not connected.")
                        break
                     
                     brightness_adjustment_complete = False
                     # Does this need to be on a per screen basis?
                     # TODO: Move this
                     # These values are the manufacturers max and min brightness in Lux
                     location_min_lux = (config["location_min_lux"])
                     location_max_lux = (config["location_max_lux"])

                     # This is the max and min brightness in Lux set for the specific display location
                     absolute_min_lux = (config["absolute_min_lux"])
                     absolute_max_lux = (config["absolute_max_lux"])

                     my_logger.debug (f"Location Min: [{location_min_lux}]")
                     my_logger.debug (f"Location Max: [{location_max_lux}]")
                     my_logger.debug (f"Display Max: [{absolute_max_lux}]")

                     # These values represent the max and min location brightness in control steps
                     max_brightness = round(location_max_lux/(absolute_max_lux/255))
                     min_brightness = round(location_min_lux/(absolute_max_lux/255))

                     my_logger.debug(f"Brightness range (0 - 255). Min: {min_brightness}. Max: {max_brightness}")
                     my_logger.info(f"Brightness Percentage. Min: {((min_brightness/255)*100)}%. Max: {((max_brightness/255)*100)}%")

                     # Check the brightness values are within the specified range of the display
                     if ( ( min_brightness < 0 ) or ( max_brightness > 255) ):
                        my_logger.error(f"Brightness values are out of range (0 - 255). Min: {min_brightness}. Max: {max_brightness}")
                        message = "BRIGHTNESS SETTING ERROR: Check the brightness settings in config.json. Brightness has not be changed"
                        EXIT_CODE = CRITICAL
                        return

                     my_logger.debug(f"Current time is: {current_time}")
                     # This is the time that the display will be off (0lux) default is 0000 as per PLG 05/23 10.6 Note 2
                     off_time = current_time.replace(hour=1, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)

                     # Turn the display off (0 lux) if it is within off_time
                     if (off_time - timedelta(minutes=minute_tolerance) <= current_time <= off_time + timedelta(minutes=minute_tolerance) and brightness_adjustment_complete == False):
                        my_logger.info(f"Current time: {current_time} is within Turn off time: {off_time}")
                        brightness_level = 0
                        # Set the brightness
                        set_module_brightness(port_value, brightness_level)
                        brightness_adjustment_complete = True
                        break

                     # Check if current time is within the range of sunset - dusk
                     if (sunset_time - timedelta(minutes=minute_tolerance) <= current_time <= dusk_time + timedelta(minutes=minute_tolerance) and brightness_adjustment_complete == False):

                        my_logger.debug(f"Current time: {current_time} is within sunset: {sunset_time} and dusk: {dusk_time}")

                        brightness_level = max_brightness
                        
                        # Calculate total duration in 5-minute intervals
                        total_duration = (dusk_time - sunset_time).total_seconds() / 60  # Duration in minutes
                        total_intervals = int(total_duration // time_interval)  # Number of 5-minute intervals

                        # Calculate the step decrement for brightnesssunset_time
                        brightness_step = (min_brightness - max_brightness) / total_intervals

                        my_logger.debug(f"Intervals: {total_intervals}, Brightness Step: {brightness_step}")

                        # Gradually adjust brightness
                        for i in range(1, total_intervals + 1):
                           
                           # Calculate the current brightness
                           brightness_level = brightness_level + brightness_step
                           brightness_level = round(brightness_level)

                           # If we pass dusk time or have surpassed the min brightness, set the miniumum brightness and exit the loop
                           if ( (current_time > dusk_time) or (brightness_level <= min_brightness) ):
                              my_logger.info("Dusk time or minimal brightness passed. Brightness set to minimum")
                              set_module_brightness(port_value, min_brightness)
                              brightness_adjustment_complete = True
                              break
                           
                           # Set the brightness
                           set_module_brightness(port_value, brightness_level)

                           # Wait for time_interval in minutes before the next adjustment
                           if testing:
                              time.sleep(time_interval)  # Fast execution during testing
                           else:
                              time.sleep(time_interval * 60)

                     # Check if current time is within the range of dawn - sunrise
                     elif (dawn_time - timedelta(minutes=minute_tolerance) <= current_time <= sunrise_time + timedelta(minutes=minute_tolerance) 
                     and brightness_adjustment_complete == False):
                        my_logger.debug(f"Current time: {current_time} is within dawn: {dawn_time} and sunrise: {sunrise_time}")

                        brightness_level = min_brightness
                        
                        # Calculate total duration in 5-minute intervals
                        total_duration = (sunrise_time - dawn_time).total_seconds() / 60  # Duration in minutes
                        total_intervals = int(total_duration // time_interval)  # Number of 5-minute intervals

                        # Calculate the step increment for brightness
                        brightness_step = (max_brightness - min_brightness) / total_intervals

                        my_logger.debug(f"Intervals: {total_intervals}, Brightness Step: {brightness_step}")

                        # Gradually adjust brightness
                        for i in range(1, total_intervals + 1):

                           current_time = datetime.now(timezone.utc)

                           # Calculate the current brightness
                           brightness_level = brightness_level + brightness_step
                           brightness_level = round(brightness_level)
                           
                           # If we pass sunrise time or have surpassed the max brightness, set the miniumum brightness and exit the loop
                           if ( (current_time > sunrise_time) or (brightness_level >= max_brightness) ):
                                 my_logger.debug("Sunrise time or maximum brightness passed. Brightness set to maximum")
                                 set_module_brightness(port_value, max_brightness)
                                 brightness_adjustment_complete = True
                                 break
                           
                           # Set the brightness
                           set_module_brightness(port_value, brightness_level)

                           # Wait for 5 minutes before the next adjustment
                           if testing:
                              time.sleep(time_interval)  # Fast execution during testing
                           else:
                              time.sleep(time_interval * 60)    
                     else:
                        message = "Automatic Brightness script was called but no brightness adjustment was done. Check daylight_times.json and script current time is functioning correctly"
                        EXIT_CODE = CRITICAL
                        break

                     my_logger.debug(f"*********End of checking times. brightness_adjustment_complete = {brightness_adjustment_complete}, port_value = {port_value}")
                        
                     if (brightness_adjustment_complete == True and port_value == no_of_receiver_cards):
                        message = "Automatic Brightness script complete"
                        EXIT_CODE = GOOD
                     else:
                        break
                     #################################################################################################
                  if (EXIT_CODE == CRITICAL):
                     break

            ##############################################################################################
            ser.close()
            i += 1
            my_logger.info("Writing to JSON file")
            #write_data('status.json', status, LOGGER_NAME) # This could go to the end to include EXIT_CODE and output message
    else:# No devices were found - exit
        message = "NO DEVICE - make sure a valid controller is connected, that the correct baudrate is defined in config.json and ensure the NOVA LCT is not running on the host system"
        EXIT_CODE = CRITICAL
        my_logger.info ("EXIT CODE: {}, {}".format(EXIT_CODE, message))
    
    my_logger.info ("EXIT CODE: {}, {}".format(EXIT_CODE, message))              
    return (EXIT_CODE)
# ------------------------------------------------------------------------------------------------------------
# FUNCTION DEFINITIONS
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
                              # status[port] = {} 
                              # status[port]["lastUpdated"] = last_updated
                              # status[port]["connectedControllers"] = device_found
                              # status[port]["targetPort"] = port
                              # status[port]["controllerDescription"] = desc
                              # status[port]["controllerHardware"] = hwid
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
                     model="Unkown"
      else:
          model="N/A"
   else:
      logger.warning("No data available at the input buffer")
      model="N/A"
   #status[port]["controllerModel"] = model
   logger.info("Sender card model: " + model)
   return (model)

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
                     DVI_valid = "Unkown"
      else:
         DVI_valid = "N/A"
   else:
         logger.warning("No data available at the input buffer")
         DVI_valid = "N/A"
   #status[port]["DVISignal"] = DVI_valid
   logger.info("DVI signal: "+ DVI_valid)
   return (DVI_valid)

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
      

def set_module_brightness(port, brightness):
# ---------------------------------------------------------------------------------------
# SCREEN BRIGHTNESS SETTINGS
# This needs to be on a per receiver card basis or global?
# ---------------------------------------------------------------------------------------
   logger = logging.getLogger(LOGGER_NAME)
   if not (0 <= brightness <= 255):
      raise ValueError("Brightness must be between 0 and 255")

   # Convert the brightness value to a byte
   brightness_byte = brightness.to_bytes(1, byteorder="big")  # Converts to a single byte

   # Update bytes 19 to 23 in the COMMANDS["set_brightness"]
   for i in range(18, 23):
      COMMANDS["set_brightness"][i] = brightness_byte[0]

   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in COMMANDS["set_brightness"]))
   get_brightness_send = methods.checksum(COMMANDS["set_brightness"])
   ser.write (get_brightness_send)
   time.sleep (sleep_time)
   if ser.inWaiting()>0:
      response = ser.read(size=ser.inWaiting())
      rx_data = list(response)
      logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
      if check_response(rx_data):
         if ( (rx_data[0] == 0xAA) and (rx_data[1] == 0x55) ):
            logger.info(f"{datetime.now().strftime('%d-%m-%Y %H:%M:%S')} Screen brightness set to: {brightness}.")
         else:
            logger.error("Error setting brightness")


def read_daylight_times(filename="daylight_times.json"):
    logger = logging.getLogger(LOGGER_NAME)
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            data = json.load(file)

        # Check if 'sun_times' exists and contains the necessary keys
        if "sun_times" in data:
            sun_times = data["sun_times"]
            return {
                "sunset_time": datetime.fromisoformat(sun_times["sunset"]),
                "dusk_time": datetime.fromisoformat(sun_times["dusk"]),
                "dawn_time": datetime.fromisoformat(sun_times["dawn"]),
                "sunrise_time": datetime.fromisoformat(sun_times["sunrise"])
            }
        else:
            logger.error(f"Error: 'sun_times' not found in the JSON file.")
            return {}

    except FileNotFoundError:
        logger.error(f"Error: The file '{filename}' does not exist.")
        return {}
    except KeyError as e:
        logger.error(f"Error: Missing expected key in JSON file: {e}")
        return {}
    except Exception as e:
        logger.error(f"Error reading the JSON file: {e}")
        return {}

# ------------------------------------------------------------------------------------------------------------
# PROGRAM ENTRY POINT - this won't be run only when imported from external module
# ------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
   sys.exit(main())#exit(main())
