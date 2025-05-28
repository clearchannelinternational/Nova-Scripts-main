#!/usr/bin/env python3
import asyncio
from base_monitoring import *
base_script = base()
async def main(reader, writer):
   await base_script.initialize_program(reader, writer)
   exit_code = base_script.UNKNOWN
   monitor_message = "check_brightness"
   output = []
   if (base_script.device_found == 0):
      message = "NO DEVICE - make sure a valid controller is connected, that the correct baudrate is defined in config.json and ensure the NOVA LCT is not running on the host system \nThis can also mean that you don't run the tool as administrator"
      exit_code = base_script.CRITICAL
      base_script.logger.error ("EXIT CODE: {}, {}".format(exit_code, message))
      await base_script.monitoring_log_output(message,monitor_message, exit_code, reader, writer)
   
   #looping through each sender card found
   i=0
   for base_script.serial_port in sorted(base_script.valid_ports):
      i += 1
      base_script.logger.info("*******************    DEVICE {}   *******************".format(i))
      base_script.logger.info("Connecting to device on {}".format(base_script.serial_port))
      base_script.logger.info(f"connected_port={base_script.serial_port}")
      base_script.ser.port = base_script.serial_port      
      try: 
         if base_script.ser.isOpen() == False:
            base_script.ser.open()
         base_script.ser.flushInput() #flush input buffer, discarding all its contents
         base_script.ser.flushOutput() #flush output buffer, aborting current output and discard all that is in buffer
         base_script.logger.info("Opened device on port: " + base_script.ser.name) # remove at production
         # Retrieve parameters from sender cards
         brightness_value, exit_code = get_display_brightness(base_script.ser.port) 
         base_script.ser.close() #closing 
         base_script.logger.info("Writing to JSON file")
         base_script.logger.info("{} closed".format(base_script.ser.is_open)) # remove at production?

         if exit_code == base_script.GOOD and brightness_value > 0: 
            message = "Brightness OK"
            base_script.logger.info(f"{monitor_message}=0")
            base_script.logger.info(f"brightness_message={message}")
            base_script.logger.info(f"brightness_value={brightness_value}%")
            
         else:
            message = "Brightness Not OK" 
            base_script.logger.critical(f"{monitor_message}=0")
            base_script.logger.critical(f"brightness_message={message}")
            base_script.logger.critical(f"brightness_value={brightness_value}%")
      except Exception as e:
         base_script.logger.error(f"{e}")
         base_script.logger.error(f"Problem occured")      

    
   # -------------------------------------------------------------
   # TO DO
   # Include checks for brightness >0. This should be a WARNING.
   # -------------------------------------------------------------

   base_script.logger.info ("EXIT CODE: {}, {}".format(exit_code, message))
   
   # ----------------------------------------------------------------
   # TO DO
   # Consider including exit_code and output message into status.json     
   # ----------------------------------------------------------------

   await base_script.monitoring_log_output(message,monitor_message, exit_code, reader, writer)
    
#################################################################################################

def get_display_brightness(port):
# ---------------------------------------------------------------------------------------
# SCREEN BRIGHTNESS SETTINGS
# This needs to be on a per receiver card basis or global?
# ---------------------------------------------------------------------------------------
   
   base_script.logger.info("Getting current screen brightness...[TO CHECK]")
   display_brightness_send = methods.checksum(display_brightness)
   base_script.logger.debug("Sending command: "+' '.join('{:02X}'.format(a) for a in display_brightness_send))
   base_script.ser.write (display_brightness_send)
   time.sleep (base_script.sleep_time)
   if base_script.ser.inWaiting()>0:
      response = base_script.ser.read(size=base_script.ser.inWaiting())
      rx_data = list(response)
      base_script.logger.debug("Received data: "+' '.join('{:02X}'.format(a) for a in rx_data))
      if base_script.check_response(rx_data):
         brightness = rx_data[18]
         brightness_pc = round(100*brightness/255)
         base_script.logger.info("Brightness Level: "+ str(brightness))
         base_script.logger.info("Global Brightness: {}% ".format(brightness_pc))
         base_script.status[port]["brightnessLevelPC"] = brightness_pc
         base_script.status[port]["brightnessLevel"] = brightness
         exit_code = base_script.GOOD
      else:
         base_script.status[port]["brightnessLevelPC"] = "N/A"
         base_script.status[port]["brightnessLevel"] = "N/A"
         exit_code = base_script.CRITICAL
   else:
         base_script.logger.warning("No data available at the input buffer")
         base_script.status[port]["brightnessLevelPC"] = "N/A"
         base_script.status[port]["brightnessLevel"] = "N/A"
         exit_code = base_script.UNKNOWN
   return base_script.status[port]["brightnessLevelPC"], exit_code


# ------------------------------------------------------------------------------------------------------------
# PROGRAM ENTRY POINT - this won't be run only when imported from external module
# ------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":   
   base_script._logger_name = "check_brightness"
   asyncio.run(base_script.communicate_with_server(main))
