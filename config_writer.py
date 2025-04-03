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
import json
import methods
from methods import read_data, write_data, loadConfig
import re
import os
import requests

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
"check_DVI_signal" : list (b"\x55\xAA\x00\x16\xFE\x00\x00\x00\x00\x00\x00\x00\x17\x00\x00\x02\x01\x00\x83\x56"), #DVI signal checking
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
# MAIN
def main():
    global sleep_time, flash_wait_time, config_data, ser, last_updated, data
    global no_of_receiver_cards, receiver_card_found

    EXIT_CODE = UNKNOWN  # Define UNKNOWN or import it if necessary
    config_data = {}  # Initialize variable to store config data

    # Set up the logging
    my_logger = methods.get_logger(
        LOGGER_NAME, LOG_FILE, FORMATTER, LOGGER_SCHEDULE, LOGGER_INTERVAL, LOGGER_BACKUPS
    )
    my_logger.info("*" * 80)
    my_logger.info("5Eyes - Display Configuration Writer")

    # Load configuration information
    config = loadConfig(LOGGER_NAME)
    sleep_time = config["sleep_time"]
    flash_wait_time = config["flash_wait_time"]
    config_data.update({"version":1.1,
                        "sleep_time":sleep_time,
                        "flash_wait_time":flash_wait_time
                        })
    
    last_updated = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    
    modules_ok = True  # Assume all modules are OK initially

    # This information is to be taken from config.json. If not present, default values are used for initialiaiton
    my_logger.info(
        "Version: {}, Sleep Time: {}, Flash Timeout: {}".format(
            config["version"], config["sleep_time"], config["flash_wait_time"]
        )
    )

    baud_rates_list = [1048576, 115200]
    for i, test_baudrate in enumerate(baud_rates_list):
      my_logger.debug(f"Attempting to search for sender cards on baudrate: {test_baudrate}")
      
      try:
         ser = methods.setupSerialPort(test_baudrate, LOGGER_NAME)
      except Exception as e:
         my_logger.warning(f"Failed to initialize serial port at {test_baudrate}: {e}")
         continue  # Skip to the next baudrate

      device_found, valid_ports = search_devices()

      if valid_ports:
         my_logger.debug(f"Successful connection with baudrate: {test_baudrate}")
         config_data.update({"baudrate": test_baudrate})
         baudrate = test_baudrate
         break
      else:
         my_logger.debug(f"No valid devices found at baudrate: {test_baudrate}")

      if i == len(baud_rates_list) - 1:
         my_logger.warning("Reached last baudrate; no valid devices found on any port.")


    if (device_found!=0):
      i=0
      valid_devices = 0

      # serial_port represents the ports that sender cards are connected to the PC
      for serial_port in sorted(valid_ports):
         my_logger.info("*******************    DEVICE {}   *******************".format(i))
         my_logger.info("Connecting to device on {}".format(serial_port))
         ser.port = serial_port
         #Below has been heavily modified for config writer - This will attempt to open the serial port with both Baud Rates. Sucessfuly opening will result in the Baud rate being saved in the config file.
         
         try:
            my_logger.debug(f"Attempting to open serial port: {serial_port} on baudrate: {baudrate}")
            ser = methods.setupSerialPort(baudrate, LOGGER_NAME)  # Re-initialize serial port with the new baudrate
            ser.port = serial_port  # Set the serial port to the current valid port
            ser.open()  # Attempt to open the port
            
            if ser.isOpen():
               my_logger.info(f"Successfully connected on {serial_port} with baudrate {baudrate}")
               valid_devices = valid_devices + 1
               config_data[serial_port] = {}
               config_data[serial_port].update({"baudrate": baudrate})
               config_data[serial_port]["sender_card_rx_port"]={}
               try:
                  ser.flushInput() #flush input buffer, discarding all its contents
                  ser.flushOutput() #flush output buffer, aborting current output and discard all that is in buffer
                  my_logger.info("Opened device on port: " + ser.name) # remove at production
               except Exception as e1:
                  my_logger.error("Error opening serial port: " + str(e))

            else:
               my_logger.error("Error communicating with device: " + ser.name)
               continue

         except Exception as e:
            my_logger.error(f"Error opening serial port: {serial_port} - {str(e)} on baudrate: {baudrate}")
            continue
         
         # RETRIEVE PARAMETERS FROM SENDER CARDS
         # -------------------------------------
         model = get_sender_card_model(serial_port)
         get_sender_card_firmware_version(serial_port)
         get_display_brightness(serial_port)
         function_card_model = get_function_card(serial_port)
         if (function_card_model != "N/A"): # this has changed since v104 where only MFN300(B) was contemplated
               get_ambient_light_level_via_function_card(serial_port)
         else:
               get_ambient_light_level_direct(serial_port)
         get_ALS_mode_status(serial_port)
         get_ALS_mode_settings(serial_port) #Write this to Config
         get_DVI_signal_status(serial_port)

         # ONLY FOR MSD600/MSD600/MCTRL600/MCTRL610
         if (model == "MSD600/MCTRL600/MCTRL610/MCTRL660"):
               get_input_source_mode(serial_port)
               get_input_source_selected(serial_port)
               get_input_source_status(serial_port)
               
         get_cabinet_width(serial_port) # TO CHECK IF THESE SHOULD BE AT CABINET LEVEL
         get_cabinet_height(serial_port) # TO CHECK IF THESE SHOULD BE AT CABINET LEVEL
         #get_edid(serial_port) #TODO
         #get_redundant_status(serial_port)   
         #get_test_mode(serial_port) #TODO
         #get_calibration_mode(serial_port) #TODO
         # -------------------------------------
         receiver_card_found = True
         no_of_receiver_cards = 0
         total_reciever_cards = 0 
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
         tx_ports_connected = []
         if (model == "MSD600/MCTRL600/MCTRL610/MCTRL660"):
            no_of_rxcardports = 4
         else:
            no_of_rxcardports = 2
         port_range = range(no_of_rxcardports)
         try:
            # sender_output_port represents the RJ45 Port on the sender card
            for sender_output_port in port_range:
               no_of_receiver_cards = 0
               config_data[serial_port]["sender_card_rx_port"][sender_output_port]={}
               config_data[serial_port]["sender_card_rx_port"][sender_output_port]["receiverCard"]={}
               my_logger.debug(f"Port Value: {sender_output_port} - Port Range: {port_range} - Reciever card number: {no_of_receiver_cards}")
               receiver_card_found = True

               for command_name, command_template in COMMANDS.items():
                  COMMANDS[command_name][7] = sender_output_port 

               while(receiver_card_found):
                  my_logger.info("=======================================================================")
                  my_logger.debug(f"*********** Sender Card Port: {sender_output_port}: Reciever Number: {no_of_receiver_cards} ***********")   
                  if (not get_receiver_connected(serial_port)):  
                     my_logger.info(f"Receiver card {no_of_receiver_cards} not connected.")
                     break
                     # if (sender_output_port == no_of_rxcardports):
                     #    message = "All sender card ports have been checked"
                     #    EXIT_CODE = GOOD
                     #    receiver_card_found = False
                     #    break
                     # else:
                     #    receiver_card_found = True
                     #    my_logger.debug(f"Next sender card port to be checked")  
                     #    continue
                  # else:
                  #    tx_ports_connected.append(sender_output_port)
                  # ---------------------------------------
                  # RETRIEVE PARAMETERS FROM RECEIVER CARDS
                  # ---------------------------------------
         
                  config_data[serial_port]["sender_card_rx_port"][sender_output_port]["receiverCard"][no_of_receiver_cards]={}

                  rx_card_model = get_receiver_card_model(serial_port, sender_output_port) #not necessary 
                  rx_card_firmware = get_receiver_card_firmware(serial_port, sender_output_port) #not necessary
                  brightness_pc, brightness, red, green, blue, vRed = get_receiver_brightness(serial_port, sender_output_port)
                  #get_ribbon_cable_status(serial_port) #required
                  temp_valid, temperature, voltage_valid, voltage = get_receiver_temp_voltage(serial_port, sender_output_port) #not necessary 
                  cabinet_lock_mode = get_cabinet_lock_mode(serial_port, sender_output_port) #required
                  #get_gamma_value(serial_port) #not necessary
                  # -------------------------------------
                     
                  #TESTING - v106
                  #number_of_modules, modules_ok = get_module_flash(serial_port,  modules_ok) #required
                  #get_module_status(serial_port, number_of_modules, sender_output_port)
                  #get_status_two(serial_port)

                  try:
                     number_of_modules = get_user_input("number_of_modules", "Number of modules per reciever card")
                     data_groups = get_user_input("data_groups", "Number of data groups per module")
                  except Exception as e:
                     message = f"A user input error has occurred: {str(e)}"
                     EXIT_CODE = CRITICAL
                     my_logger.info ("EXIT CODE: {}, {}".format(EXIT_CODE, message))
                     my_logger.info("Writing to JSON file")
                     write_data('config.json', config_data, LOGGER_NAME) # This could go to the end to include EXIT_CODE and output message
                  get_status_three(serial_port, sender_output_port)
                  #################################################################################################
                  no_of_receiver_cards = no_of_receiver_cards + 1
                  total_reciever_cards = total_reciever_cards + 1
                     
         except Exception as e:
            message = f"An error has occurred connecting to the Reciever Card: {str(e)}"
            ser.close()
            i += 1
            my_logger.info("Writing to JSON file")
            write_data('config.json', config_data, LOGGER_NAME) # This could go to the end to include EXIT_CODE and output message
            
         try:
            no_of_txcardports = get_user_input("no_of_txcardports", "Number of sender card ports in use")
            absolute_min_lux = get_user_input("absolute_min_lux", "Minimum Brightness in Lux for the display as per the manufacturers specifications")
            absolute_max_lux = get_user_input("absolute_max_lux", "Maximum Brightness in Lux for the display as per the manufacturers specifications")
            location_min_lux = get_user_input("location_min_lux", "Minimum Brightness in Lux for the display as specified for the specific location")
            location_max_lux = get_user_input("location_max_lux", "Maximum Brightness in Lux for the display as specified for the specific location")
            display_location = get_location()
            config_data.update({
                              "no_of_sender_cards": valid_devices,
                              "receiver_cards": total_reciever_cards,
                              "no_of_txcardports": no_of_txcardports,
                              "absolute_min_lux": absolute_min_lux,
                              "absolute_max_lux": absolute_max_lux,
                              "location_min_lux": location_min_lux,
                              "location_max_lux": location_max_lux,
                              "tx_ports_connected": tx_ports_connected,
                              "display_location": display_location
                              })

         except Exception as e:
            message = f"A user input error has occurred: {str(e)}"
            EXIT_CODE = CRITICAL
            my_logger.info ("EXIT CODE: {}, {}".format(EXIT_CODE, message))
            return EXIT_CODE
         
      my_logger.info("Writing to JSON file")
      write_data('config.json', config_data, LOGGER_NAME) # This could go to the end to include EXIT_CODE and output message
      message = """Config.json has been successfully updated
      Open Config.json and confirm values.
      Report any errors and update the errors manually in the file"""
      EXIT_CODE = GOOD

    else:# No devices were found - exit
        message = "NO DEVICE - make sure a valid controller is connected, that the correct baudrate is defined in config.json and ensure the NOVA LCT is not running on the host system"
        EXIT_CODE = CRITICAL
        return EXIT_CODE
    
    my_logger.info ("EXIT CODE: {}, {}".format(EXIT_CODE, message))
    # ----------------------------------------------------------------
    # TO DO
    # Consider including EXIT_CODE and output message into status.json     
    # ----------------------------------------------------------------           
    return exit (EXIT_CODE)
# ------------------------------------------------------------------------------------------------------------
# FUNCTION DEFINITIONS
#################################################################################################
#  Update a specific key in the JSON config file with a new value.
#  Currently only used with config.json but the filename is there should this be required for
#  other .json.
#  Inputs:
#     key (str): The key in the JSON file to update.
#     value: The new value to set for the key. This is set to santise the input to only numeric values
#     description: This will be displayed to the user who is running the script
#     filename (str): The file name of the JSON file (default is 'config.json').
#     EXAMPLE: update_config({
#                        "api_key": {"value": "12345", "description": "API key for authentication"},
#                         "timeout": {"value": "ASK_USER", "description": "Timeout duration in seconds"})
#
def update_config(updates, filename="config.json"):
    
    logger = logging.getLogger(LOGGER_NAME)
    
    # Ensure the file is written in the same directory as the script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(script_dir, filename)
    
    try:
        # Load existing config if file exists, otherwise initialize an empty dictionary
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                config_data = json.load(f)
        else:
            config_data = {}

        for key, details in updates.items():
            value = details.get("value")
            description = details.get("description")

            if description:
                print(f"Description: {description}")  # Display description to user if provided
            
            # Check if the value is specific (e.g., a placeholder) and prompt the user
            if value == "ASK_USER":
                logger.info(f"Value for '{key}' is set to 'ASK_USER'. Prompting user for input.")
                while True:
                    user_input = input(f"Please enter a numeric value for '{key}': ").strip()
                    if user_input and user_input.isdigit():
                        value = user_input
                        logger.info(f"User entered numeric value: {value}")
                        break
                    else:
                        print("Invalid input. Please enter only numbers, without any spaces, special characters, or letters.")
            
            # Update the specific key
            config_data[key] = value
            logger.info(f"Updating '{key}' to '{value}' in {file_path}.")
        
        # Write updated config back to file
        with open(file_path, 'w') as f:
            json.dump(config_data, f, indent=4)

        logger.info(f"Configuration updated successfully in {file_path}.")
    
    except Exception as e:
        logger.error(f"Error updating config file: {e}")


#  Prompts the user for a numeric input and validates the input.
#  A function to get user input with validation.
   
#  :param variable_name: Name of the variable to request from the user.
#  :param description: Description of the variable.
#  :param data_type: Type of expected input ("numeric" or "text").
#  :return: The validated user input.
#  - int: The validated numeric input from the user.

def get_user_input(variable_name, description, data_type="numeric"):
    logger = logging.getLogger(LOGGER_NAME)
    
    logger.info(f"Requesting input for {variable_name}: {description}")

    while True:
        user_input = input(f"{'*' * 40} Please enter {variable_name}: ").strip()

        if data_type == "numeric":
            try:
                value = float(user_input)  # Allows decimal numbers
                logger.info(f"User entered numeric value: {value} for '{variable_name}'")
                return value
            except ValueError:
                print("Invalid input. Please enter a valid numeric value (integers or decimals only).")
        
        elif data_type == "text":
            if user_input:  # Ensures input is not empty
                logger.info(f"User entered text value: '{user_input}' for '{variable_name}'")
                return user_input
            else:
                print("Invalid input. Please enter a valid text value.")

        elif data_type == "yes_no":
            if user_input.lower() in ["yes", "y"]:
                return True
            elif user_input.lower() in ["no", "n"]:
                return False
            else:
                print("Invalid input. Please enter 'yes' or 'no'.")

def get_location():
   logger = logging.getLogger(LOGGER_NAME)

   try:
      # Fetch location data from ipinfo.io
      response = requests.get("https://ipinfo.io", timeout=5)
      response.raise_for_status()
      data = response.json()

      latlong = data.get("loc").split(",")
      location_data = {
         "city": data.get("city"),
         "region": data.get("region"),
         "timezone": data.get("timezone"),
         "latitude": float(latlong[0]),
         "longitude": float(latlong[1])
      }

      # Log and display fetched location data
      logger.info(f"Fetched location data: {json.dumps(location_data, indent=4)}")

      # Ask the user if they want to modify the location data
      modify_location = get_user_input("Modify location?", "Would you like to manually change this data? (yes/no)", data_type="yes_no")
      
      if not modify_location:
         return location_data  # Return the fetched data if user accepts it

      # If the user wants to modify the data, fall into the manual input flow
      raise ValueError("User chose to manually enter location data.")

   except (requests.RequestException, ValueError, AttributeError, KeyError) as e:
      logger.error(f"Fetching location failed or user requested manual entry: {e}")

      # Request user input for missing location data using get_user_input
      location_data = {
         "city": get_user_input("city", "Enter your city name", data_type="text"),
         "region": get_user_input("region", "Enter your region/state name", data_type="text"),
         "timezone": get_user_input("timezone", "Enter your timezone (e.g., America/New_York)", data_type="text"),
         "latitude": get_user_input("latitude", "Enter your latitude coordinate", data_type="numeric"),
         "longitude": get_user_input("longitude", "Enter your longitude coordinate", data_type="numeric"),
      }

      # Log the manually entered location data before returning
      logger.info(f"Manually entered location data: {json.dumps(location_data, indent=4)}")

      return location_data

# ------------------------------------------------------------------------------------------------------------
# SHARED FUNCTIONS
# ------------------------------------------------------------------------------------------------------------

def get_status_two(port):
#-----------------------------------------------------------------
   global no_of_receiver_cards
   global number_of_modules
   number_of_modules = 4
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

   # Define signal line mapping for each 16-bit flat cable pair
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
        13: "B_addr",
        14: "C",
        15: "D"
    }
   
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
         #config_data[port]["receiverCard"][no_of_receiver_cards]["module"]={}
         if check_response(rx_data):
            # Read X0-X23 bytes for each module expected
            # First, read the X0 byte for LED module status
            # Next, check flat cable data in bytes X22 and X23.
            # The Data Groups consist of 2 bytes (16 bits). Each bit is a Data Flag
            for j in range (int(number_of_modules)):
               #config_data[port]["receiverCard"][no_of_receiver_cards]["module"][j]={}
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
               #config_data[port]["receiverCard"][no_of_receiver_cards]["module"][j]=module_sts
         else:
            modules_ok = modules_ok and False
            #config_data[port]["receiverCard"][no_of_receiver_cards]["module"]='N/A'
   else:
         logger.warning ("No data available at the input buffer")    
         number_of_modules = 0
         modules_ok = modules_ok and False
         module_status="N/A"    
         #config_data[port]["receiverCard"][no_of_receiver_cards]["module"]="N/A"
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
                              config_data[port] = {} 
                              config_data[port]["lastUpdated"] = last_updated
                              config_data[port]["connectedControllers"] = device_found
                              config_data[port]["targetPort"] = port
                              config_data[port]["controllerDescription"] = desc
                              config_data[port]["controllerHardware"] = hwid
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
   config_data[port]["controllerModel"] = model
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
   config_data[port]["controllerFirmware"] = firmware
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
   config_data[port]["inputSourceMode"] = video_mode
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
   config_data[port]["inputSourcePort"] = video_port
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
   config_data[port]["inputSourceStatus"] = source_status
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
   config_data[port]["DVISignal"] = DVI_valid
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
   config_data[port]["ALSMode"] = ALS_mode
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
         config_data[port]["ALSQuantity"] = rx_data[18]

         max = (rx_data[23]<<8) + rx_data[22]
         logger.info  ("Max Lux: {}".format(max))
         config_data[port]["maxLux"] = max

         min = (rx_data[25]<<8)+ rx_data[24]
         logger.info  ("Min Lux: {}".format(min))
         config_data[port]["minLux"] = min

         max_brightness = rx_data[26]
         max_brightness_pc=int(100*max_brightness/255)
         logger.info("Max Brightness (0-255): {}".format(max_brightness))
         logger.info  ("Max Brightness: {}% ".format(max_brightness_pc))
         config_data[port]['maxBright'] = max_brightness
         config_data[port]["maxBrightPC"] = max_brightness_pc

         min_brightness = rx_data[27]
         min_brightness_pc= int(100*min_brightness/255)
         logger.info("Min Brightness (0-255): {}".format(min_brightness))
         logger.info  ("Min Brightness: {}% ".format(min_brightness_pc))
         config_data[port]['minBright'] = min_brightness
         config_data[port]["minBrightPC"] = min_brightness_pc

         logger.info  ("Number of steps: {}".format(rx_data[28]))
         config_data[port]["numSteps"] = rx_data[28]
         logger.info  ("Light Sensor Position: {}".format(rx_data[49]))
         config_data[port]["ALSPosition"] = rx_data[49]
         logger.info  ("Port Address Position: {}".format(rx_data[50]))
         config_data[port]["PortPosition"] = rx_data[50]
         logger.info  ("Function Card Position: {} {}".format(hex(rx_data[42]),hex(rx_data[41])))

         config_data[port]["functionCardPosition (LOW)"] = hex(rx_data[41])
         config_data[port]["functionCardPosition (HIGH)"] = hex(rx_data[21])
         logger.info  ("Address of sensor on Function Card: {}".format(rx_data[43]))
         config_data[port]["functionCardAddress"] = rx_data[43]
      else:
         config_data[port]["ALSQuantity"] = 'N/A'
         config_data[port]["maxLux"] = 'N/A'
         config_data[port]["minLux"] = 'N/A'
         config_data[port]['maxBright'] = 'N/A'
         config_data[port]["maxBrightPC"] = 'N/A'
         config_data[port]['minBright'] = 'N/A'
         config_data[port]["minBrightPC"] = 'N/A'
         config_data[port]["minBrightNits"] = 'N/A'
         config_data[port]["numSteps"] = 'N/A'
         config_data[port]["ALSPosition"] = 'N/A'
         config_data[port]["PortPosition"] = 'N/A'
         config_data[port]["functionCardPosition"] = 'N/A'
         config_data[port]["functionCardAddress"] = 'N/A'
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
   config_data[port]["ambientLightLevel"] = ambient_light_lux
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
   config_data[port]["ambientLightLevel"] = ambient_light_lux
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
         config_data[port]["brightnessLevelPC"] = brightness_pc
         config_data[port]["brightnessLevel"] = brightness
         config_data[port]["brightnessLevelNits"] = brightness_nits
         config_data[port]["redLevel"] = rx_data[19]
         config_data[port]["greenLevel"] = rx_data[20]
         config_data[port]["blueLevel"] = rx_data[21]
         config_data[port]["vRedLevel"] = rx_data[22]
      else:
         config_data[port]["brightnessLevelPC"] = "N/A"
         config_data[port]["brightnessLevel"] = "N/A"
         config_data[port]["brightnessLevelNits"] = "N/A"
         config_data[port]["redLevel"] = "N/A"
         config_data[port]["greenLevel"] = "N/A"
         config_data[port]["blueLevel"] = "N/A"
         config_data[port]["vRedLevel"] = "N/A"         
   else:
         logger.warning("No data available at the input buffer")
         config_data[port]["brightnessLevelPC"] = "N/A"
         config_data[port]["brightnessLevel"] = "N/A"
         config_data[port]["brightnessLevelNits"] = "N/A"
         config_data[port]["redLevel"] = "N/A"
         config_data[port]["greenLevel"] = "N/A"
         config_data[port]["blueLevel"] = "N/A"
         config_data[port]["vRedLevel"] = "N/A"

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

def get_receiver_card_model(port, sender_output_port):
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
      logger.info ('Receiver card model: {}'.format(model))
   else:
      logger.warning("No data available at the input buffer")
      receiver_card_found = False

   config_data[port]["sender_card_rx_port"][sender_output_port]["receiverCard"][no_of_receiver_cards] = {"receiverModel": model}
   return (model)

def get_receiver_card_firmware(port, sender_output_port):
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
   config_data[port]["sender_card_rx_port"][sender_output_port]["receiverCard"][no_of_receiver_cards] = {"receiverFPGA": FPGA}
   logger.info('Receiver Card FPGA Firmware version: {}'.format(FPGA))

   return (FPGA)

def get_receiver_temp_voltage(port, sender_output_port):
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
   config_data[port]["sender_card_rx_port"][sender_output_port]["receiverCard"][no_of_receiver_cards].update({
    "tempValid": temp_valid,
    "temperature": temperature,
    "voltageValid": voltage_valid,
    "voltage": voltage,
    "monitorCard": monitoring_card
   })

   return (temp_valid, temperature, voltage_valid, voltage)

def get_cabinet_kill_mode(port, sender_output_port):
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
   #config_data[port]["receiverCard"][no_of_receiver_cards]["kill"]=kill
   config_data[port]["sender_card_rx_port"][sender_output_port]["receiverCard"][no_of_receiver_cards] = {"kill": kill}
   return cabinet_on

def get_cabinet_lock_mode(port, sender_output_port):
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
   #config_data[port]["receiverCard"][no_of_receiver_cards]["locked"]=lock
   config_data[port]["sender_card_rx_port"][sender_output_port]["receiverCard"][no_of_receiver_cards] = {"locked": lock}
   return (lock)

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
   config_data[port]["receiverCard"][no_of_receiver_cards]["gamma"]=gamma

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
            time.sleep(2
                       ) # this may have to be more than 1 second and perhaps minuimum 20s
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
         #config_data[port]["receiverCard"][no_of_receiver_cards]["module"]={}
         if check_response(rx_data):
            for j in range (int(number_of_modules)):
               #config_data[port]["receiverCard"][no_of_receiver_cards]["module"][j]={}
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
               #config_data[port]["receiverCard"][no_of_receiver_cards]["module"][j]=module_status
         else:
            modules_ok = modules_ok and False
            #config_data[port]["receiverCard"][no_of_receiver_cards]["module"]='N/A'
   else:
         logger.warning ("No data available at the input buffer")    
         number_of_modules = 0
         modules_ok = modules_ok and False
         module_status="N/A"    
         #config_data[port]["receiverCard"][no_of_receiver_cards]["module"]="N/A"
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
               config_data[port]["receiverCard"][no_of_receiver_cards]["G{firstByte}, G{secondByte}".format(firstByte=k, secondByte=k+1)]="{one:04b}, {two:04b}".format(one=data[x]>>4, two=data[x] & 0x0F)
               k=k+2
            logger.info("A = {:08b}".format(data[8]))
            config_data[port]["receiverCard"][no_of_receiver_cards]["A"]="{:08b}".format(data[8])    
            logger.info("B = {:08b}".format(data[9]))
            config_data[port]["receiverCard"][no_of_receiver_cards]["B"]="{:08b}".format(data[9])   
            logger.info("C = {:08b}".format(data[10]))
            config_data[port]["receiverCard"][no_of_receiver_cards]["C"]="{:08b}".format(data[10])
            logger.info("D = {:08b}".format(data[11]))
            config_data[port]["receiverCard"][no_of_receiver_cards]["D"]="{:08b}".format(data[11])    
            logger.info("LAT = {:08b}".format(data[12]))
            config_data[port]["receiverCard"][no_of_receiver_cards]["LAT"]="{:08b}".format(data[12])
            logger.info("OE = {:08b}".format(data[13]))
            config_data[port]["receiverCard"][no_of_receiver_cards]["OE"]="{:08b}".format(data[13])
            logger.info("DCLK = {:08b}".format(data[14]))
            config_data[port]["receiverCard"][no_of_receiver_cards]["DCLK"]="{:08b}".format(data[14])
            logger.info("CTRL = {:08b}".format(data[15]))
            config_data[port]["receiverCard"][no_of_receiver_cards]["CTRL"]="{:08b}".format(data[15])
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
   #config_data[port]["receiverCard"][no_of_receiver_cards]["gamma"]=gamma

def get_receiver_brightness(port, sender_output_port):
# ---------------------------------------------------------------------------------------
# SCREEN BRIGHTNESS SETTINGS
# This needs to be on a per receiver card basis or global?
# -----------------------------------------------------------------------------------------------
    global no_of_receiver_cards
    logger = logging.getLogger(LOGGER_NAME)
    
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

            config_data[port]["sender_card_rx_port"][sender_output_port]["receiverCard"][no_of_receiver_cards].update({
               "brightnessLevelPC": brightness_pc,
               "brightnessLevel": brightness,
               "redLevel": red,
               "greenLevel": green,
               "blueLevel": blue,
               "vRedLevel": vRed})
            return brightness_pc, brightness, red, green, blue, vRed  
        else:
            logger.warning("Invalid response received.")

    else:
        logger.warning("No data available at the input buffer")

    # If no data or invalid response, return "N/A"
    config_data[port]["receiverCard"][no_of_receiver_cards] = {
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
         config_data[port]["brightnessLevelPC"] = brightness_pc
         config_data[port]["brightnessLevel"] = brightness
      else:
         config_data[port]["brightnessLevelPC"] = "N/A"
         config_data[port]["brightnessLevel"] = "N/A"
         brightness_pc = "N/A"
         brightness = "N/A"
   else:
         logger.warning("No data available at the input buffer")
         config_data[port]["brightnessLevelPC"] = "N/A"
         config_data[port]["brightnessLevel"] = "N/A"
         brightness_pc = "N/A"
         brightness = "N/A"

   return brightness_pc, brightness

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
   config_data[port]["functionCardModel"] = model
   logger.info("Function card model: " + model)
   return (model)

def get_module_status(port, no_of_modules, sender_output_port):
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
   data_groups_per_module = 4
   no_of_modules = 4
   config_data[port]["sender_card_rx_port"][sender_output_port]["receiverCard"][no_of_receiver_cards]["module"] = {}

   
   logger = logging.getLogger(LOGGER_NAME)
   reciever_card_connected = True
   reciever_card = 0
   logger.info(f"Getting receiver card number {reciever_card} status")
   COMMANDS["get_status"][8] = no_of_receiver_cards 
   response_length = ( no_of_modules * ( 22 + 2 * data_groups_per_module ) )
   #logger.debug(f"Data Size: {response_length}")
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
      logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))

   #TESTING CODE 
   #expected_hex = "AA5500C400FE0100010000000A00000A7800FF8028ADB073160200000000000000000000000000008001800180018001FF8026AD245C140200000000000000000000000000008001800180018001FF802AADA481140200000000000000000000000000008001800180018001FF8024AC1455000000000000000000000000000000008001800180018001756C"
   #expected_bytes = bytes.fromhex(expected_hex)
   #rx_data = list(expected_bytes)

   #logger.info(f"expected_bytes {expected_bytes}")
   #logger.info(f"rx_data: {rx_data}")

   #logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
   #data_size = (len(rx_data))
   #logger.debug(f"Response Data Size: {data_size}")
   
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
      #for module_name, (data, module_number) in modules.items():
         #logger.debug(f"{module_name}: {data}, Number: {module_number}")

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

      # Check each module and update module status
      # Check each module and update module status
      for module_name, (modules, module_number) in modules.items():
         logger.debug(f"Receiver Card {reciever_card}")
         module_status = modules[0]
         
         if module_status == 0xFF:
            status = "functioning"
            logger.debug(f"   Module {module_number} is functioning")
         elif module_status == 0x00:
            status = "not functioning"
            logger.error(f"   Module {module_number} is not functioning correctly")
            flag_module_error = True
         else:
            status = "detection error"
            logger.error(f"   Module {module_number} Detection error")
            flag_module_error = True

         # Update module status in config_data
         config_data[port]["sender_card_rx_port"][sender_output_port]["receiverCard"][no_of_receiver_cards]["module"].update({
            f"module {module_number}": {
                  "status": status,
                  "faulty_lines": []
            }
         })

      # Handle flat cable data and update module line status
      for module_index in range(no_of_modules):
         byte1, byte2 = flat_cable_data[module_index * 2: module_index * 2 + 2]
         module_number = module_index + 1

         for byte_index, byte in enumerate([byte1, byte2]):
            for bit_position in range(8):
                  if (byte >> bit_position) & 1:
                     line_index = byte_index * 8 + bit_position
                     line_name = signal_lines.get(line_index, "Unknown Line")
                     logger.error(f"Fault detected in module {module_number} Line: {line_name}")

                     # Append faulty line info to the respective module
                     config_data[port]["sender_card_rx_port"][sender_output_port]["receiverCard"][no_of_receiver_cards]["module"][f"module {module_number}"]["faulty_lines"].append(line_name)

      # Log the overall status of modules
      if flag_module_error:
         logger.info("  One or more modules reported faults.")
      else:
         logger.info("All modules are functioning correctly.")
         
      reciever_card = reciever_card + 1
   else:
      logger.warning("No data available at the input buffer")

def get_status_three(port, sender_output_port):
    global no_of_receiver_cards
    global number_of_modules

    # This is to be uncommented when config.json is setup
    # number_of_modules = config["number_of_modules"]
    # data_groups = config["data_groups"]

    FAULT_CRITICAL_LINES = {
                           "RFU": False,  # Change to True if you want RFU to cause module faults
                           "R": False     # Change to True if R should cause module faults
                           }


    number_of_modules = 4
    data_groups = 4
    element_length = 22 + (2 * data_groups)

    logger = logging.getLogger(LOGGER_NAME)
    logger.info("Getting module status")

    COMMANDS["check_module_status"][8] = no_of_receiver_cards
    data_length = number_of_modules * element_length
    first_byte = (data_length & 0xFF00) >> 8
    second_byte = data_length & 0x00FF
    COMMANDS["check_module_status"][16] = second_byte
    COMMANDS["check_module_status"][17] = first_byte

    check_module_status_send = methods.checksum(COMMANDS["check_module_status"])
    logger.debug("Sending command: " + ' '.join('{:02X}'.format(a) for a in check_module_status_send))
    ser.write(check_module_status_send)
    time.sleep(sleep_time)

    modules_ok = True

    # Define signal line mapping for each 16-bit flat cable pair
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
        13: "B_addr",
        14: "C",
        15: "D"
    }

    if ser.inWaiting() > 0:
        response = ser.read(size=ser.inWaiting())
        rx_data = list(response)
        logger.debug("Received data: " + ' '.join('{:02X}'.format(a) for a in rx_data))

        if check_response(rx_data):
            config_data[port]["sender_card_rx_port"][sender_output_port]["receiverCard"][no_of_receiver_cards]["module"] = {}
            logger.debug("CONFIG DATA CREATED")

            for j in range(number_of_modules):
                element_start = 18 + j * element_length
                element = rx_data[element_start : element_start + element_length]
                logger.debug("MODULE STATUS: " + ' '.join('{:02X}'.format(a) for a in element))

                module_status_byte = element[0]
                if module_status_byte == 0xFF:
                    module_status = "OK"
                    modules_ok = modules_ok and True
                elif module_status_byte == 0x00:
                    module_status = "Error or no module available"
                    modules_ok = modules_ok and False
                else:
                    module_status = "Unknown module state"
                    modules_ok = modules_ok and True

                # Fault detection across 4 data groups (X22, X24, X26, X28)
                faulty_lines = []
                module_has_unmasked_fault = False

                for g in range(data_groups):
                  byte1 = element[22 + g * 2]
                  byte2 = element[23 + g * 2]
                  combined = (byte2 << 8) | byte1  # 16 bits per group

                  for bit in range(16):
                     if (combined >> bit) & 1:
                           line_name = signal_lines.get(bit, f"Line_{bit}")
                           faulty_lines.append(line_name)
                           # Check if this line is critical for triggering module fault
                           if FAULT_CRITICAL_LINES.get(line_name, True):  # default True
                              module_has_unmasked_fault = True
               
                block_fault = "FAULT" if module_has_unmasked_fault else "OK"

                # Override module status if signal lines are faulty
                if module_status_byte == 0xFF and module_has_unmasked_fault:
                   module_status = "signal line fault"
                   modules_ok = False  # mark this whole batch as not fully OK

                if faulty_lines:
                  logger.debug(f"Module {j + 1} has faults on lines: {', '.join(faulty_lines)}")

                # Log result
                logger.info(
                    "Module {module_index}: STATUS: {status} (0x{status_byte:02X})   BLOCK FAULTS: {block}".format(
                        module_index=j + 1,
                        status=module_status,
                        status_byte=module_status_byte,
                        block=block_fault,
                    )
                )

                # Store in config_data
                config_data[port]["sender_card_rx_port"][sender_output_port]["receiverCard"][no_of_receiver_cards]["module"][f"module {j+1}"] = {
                    "status": module_status,
                    "raw_status_byte": module_status_byte,
                    "faulty_lines": faulty_lines
                }
        else:
            logger.warning("Checksum failed or invalid response.")
            modules_ok = False
            number_of_modules = 0
    else:
        logger.warning("No data available at the input buffer")
        modules_ok = False
        number_of_modules = 0

    return number_of_modules, modules_ok



# ------------------------------------------------------------------------------------------------------------
# SHARED FUNCTIONS
# ------------------------------------------------------------------------------------------------------------


# ------------------------------------------------------------------------------------------------------------
# PROGRAM ENTRY POINT - this won't be run only when imported from external module
# ------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
   sys.exit(main())#exit(main())
