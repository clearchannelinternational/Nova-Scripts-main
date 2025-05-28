#!/usr/bin/env python3
import asyncio
from base_monitoring import *
base_script = base()
async def check_dvi(reader, writer):
   monitor_message = "dvi_alarm"
   output = []

   # Retrieve parameters from sender cards
   DVI = get_DVI_signal_status(base_script.ser.port)

   if DVI != "Valid":  # Check if a video input on DVI is valid
         message = "DVI SIGNAL MISSING" 
         exit_code = base_script.CRITICAL 
         base_script.logger.error(f"{monitor_message}=0")
         base_script.logger.error(f"dvi_message={message}")
   else:
         message = "DVI SIGNAL OK"
         exit_code = base_script.GOOD
         base_script.logger.info(f"{monitor_message}=0")
         base_script.logger.info(f"dvi_message={message}")
      
   # TODO: Include checks for brightness >0. This should be a WARNING.
   base_script.logger.info(f"EXIT CODE: {exit_code}, {message}")

def get_DVI_signal_status(port):
# ---------------------------------------------------------------------------------------
# DVI SIGNAL CHECK
# Device: Sending Card
# Base Address: 02000000 H 
# Data Length: 1H
# Applicable to all sender cards
# ---------------------------------------------------------------------------------------
   logger = logging.getLogger(base_script.LOGGER_NAME)
   logger.info("Getting DVI signal")
   logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in check_DVI_signal))
   base_script.ser.write (check_DVI_signal)
   time.sleep (base_script.sleep_time)
   if base_script.ser.inWaiting()>0:
      response = base_script.ser.read(size=base_script.ser.inWaiting())
      rx_data = list(response)
      logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
      if base_script.check_response(rx_data):
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
   base_script.status[port]["DVISignal"] = DVI_valid
   logger.info("DVI signal: "+ DVI_valid)
   return (DVI_valid)
