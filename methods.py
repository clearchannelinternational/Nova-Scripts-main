import serial
import serial.tools.list_ports
import json
import time
import logging
from logging.handlers import TimedRotatingFileHandler
import os 

status = {} # Initialise variable to store status data
global last_updated
#############################################################################################
#  Load configuration from a JSON file (config.json) and return its contents as a dictionary.
#  If the file does not exist or is invalid, default configuration values are used instead.
#
#  Parameters:
#  ----------
#  logger_name : str
#      The name of the logger to use for logging informational and error messages.
#
#  Returns:
#  -------
#  dict
#      A dictionary containing the configuration parameters.
#      Keys include:
#      - "version" : str : The version of the configuration (default: "Unknown").
#      - "baudrate" : int : The baud rate for serial communication (default: 115200).
#      - "sleep_time" : float : The sleep delay time in seconds (default: 0.3).
#############################################################################################
def loadConfig(logger_name):
    logger = logging.getLogger(logger_name)
    logger.info("Loading config.json")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(script_dir, "config.json")

    DEFAULT_CONFIG = {
        "version": 1.0,
        "baudrate": 115200,
        "sleep_time": 0.5,
        "flash_wait_time": 15
    }

    try:
        with open(file_path, "r") as f:
            data = json.load(f)
            return data  # Trust that config.json has all necessary keys

    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Error loading config.json: {e}. Using default parameters.")

        # Create a new config.json with default values if not found or corrupted
        with open(file_path, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
            logger.info("Created a new config.json with default values.")

        return DEFAULT_CONFIG
   
def read_data(filename,logger_name):
   logger = logging.getLogger(logger_name)
   try:
      with open(filename, "r") as read_file:
         temp_data=json.loads(read_file.read())
         logger.info('Reading from {}'.format(filename))
   except IOError: # TODO: or read from backup file
      logger.error('Error: {} not found.'.format(filename))
      temp_data = {}
   return temp_data

def write_data(filename, json_data, logger_name):
    logger = logging.getLogger(logger_name)
    
    try:
        # Ensure the file is saved in the same directory as the script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(script_dir, filename)
        
        # Convert data to JSON
        data = json.dumps(json_data, indent=4)
        
        # Write data to file
        with open(file_path, "w", encoding="utf-8") as outfile:
            outfile.write(data)
        
        logger.info(f'Written to {file_path}')
    
    except json.JSONDecodeError as e:
        logger.error(f'JSON encoding error: {e}')
    
    except IOError as e:
        logger.error(f'File error ({filename}): {e}')
    
    except Exception as e:
        logger.error(f'Unexpected error: {e}')

def checkConnections():
    port = "/dev/ttyUSB0"
    return (port)

def checksum (arg1):# Function definition for checksum calculation
    chksum = 0
    for i in range (2, len(arg1)-2):
        chksum = chksum + arg1 [i]
    chksum = chksum + 0x5555
    chksum_high = chksum & 0xFF
    chksum_low = (chksum & 0xFF00)>>8
    arg1 [len(arg1)-2]=chksum_high
    arg1 [len(arg1)-1]=chksum_low
    return arg1

def setupSerialPort(baud, logger_name):
   logger = logging.getLogger(logger_name)
   logger.info(f"Setting up serial port with baudrate {baud}")
   port = serial.Serial()
   port.baudrate = baud #Baudrate 115200f or MCTRL300 only; other devices use different baudrate
   port.bytesize =  serial.EIGHTBITS
   port.parity = serial.PARITY_NONE
   port.stopbits = serial.STOPBITS_ONE 
   port.timeout = 0
   return port

def checkConnectedDevice(port, device, sleep_time):
    port.port = device
    # TRY OPENING UP THIS PORT
    try: 
        port.open()
    except Exception as e:
        print (str(e))
    if port.isOpen():
        try:
            port.flushInput() #flush input buffer, discarding all its contents
            port.flushOutput() #flush output buffer, aborting current output and discard all that is in buffer  
            # SEND COMMAND

            # CHECK IF ANYTHING IS AT THE INPUT
            time.sleep (sleep_time)  

            #IF SO, INTERPRET IT
            #OTHERWISE MOVE ON
        except Exception as e1:
            print ("Error communicating with device...",str(e1))
        port.close()
    else:
        exit()

def get_file_handler(file, formatter, schedule, intervals, backups):
   file_handler = TimedRotatingFileHandler(file, when=schedule, encoding='utf-8', interval=intervals, backupCount=backups) # rotates log every day and stores up to 7 backups (1 week)
   file_handler.setFormatter(formatter)
   return file_handler

def get_console_handler(formatter):
   console_handler = logging.StreamHandler()
   console_handler.setFormatter(formatter)
   return console_handler

def get_logger(logger_name,log_file, log_formatter, log_schedule, log_interval, log_backups):
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG) # better to have too much log than not enough
    if logger.hasHandlers():
        logger.handlers.clear()
    logger.addHandler(get_file_handler(log_file, log_formatter, log_schedule, log_interval, log_backups))
    logger.addHandler(get_console_handler(log_formatter))  
    logger.propagate = False # with this pattern, it's rarely necessary to propagate the error up to parent
    return logger
 
